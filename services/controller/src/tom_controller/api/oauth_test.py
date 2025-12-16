"""OAuth test endpoints for development and debugging.

These endpoints are TEST/CONVENIENCE endpoints that help with OAuth flow testing.
They are restricted to localhost and must be explicitly enabled via config.
"""

import logging
import os
import yaml
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from starlette.requests import Request
from jose import jwt as jose_jwt

from tom_controller.api.auth import _jwt_auth
from tom_controller.exceptions import TomAuthException

logger = logging.getLogger(__name__)

router = APIRouter(tags=["oauth-test"])


def _ensure_localhost(request: Request):
    """Restrict endpoint to localhost only."""
    host = request.client.host if request.client else None
    if host not in {"127.0.0.1", "::1", "localhost"}:
        raise HTTPException(
            status_code=403, detail="OAuth test endpoints are restricted to localhost"
        )


class TokenRequest(BaseModel):
    """Request body for token exchange."""

    code: str
    state: str
    redirect_uri: str
    provider: Optional[str] = None
    code_verifier: Optional[str] = None


class TokenResponse(BaseModel):
    """Response for token exchange."""

    access_token: str
    token_type: str = "Bearer"
    expires_in: Optional[int] = None
    id_token: Optional[str] = None


@router.post("/oauth/token")
async def exchange_token(
    request: Request, token_request: TokenRequest
) -> TokenResponse:
    """Exchange OAuth authorization code for JWT token.

    This is a TEST/CONVENIENCE endpoint. In production, clients should handle
    OAuth flows themselves and only send validated JWTs to Tom.
    """
    import httpx

    settings = request.app.state.settings

    # Check if OAuth test endpoints are enabled globally
    if not settings.oauth_test_enabled:
        raise HTTPException(
            status_code=503,
            detail="OAuth test endpoints not enabled. Set oauth_test_enabled: true in config.",
        )

    # Restrict to localhost when test endpoints are enabled
    _ensure_localhost(request)

    # Find the validator for the requested provider (or first if not specified)
    validator = None
    provider_config = None

    for v in request.app.state.jwt_providers:
        # Find matching config
        for cfg in settings.jwt_providers:
            if cfg.enabled and cfg.name == v.name:
                if v.oauth_test_token_endpoint:
                    # Use this provider if it matches the request or no provider specified yet
                    if token_request.provider == v.name or (
                        not validator and not token_request.provider
                    ):
                        validator = v
                        provider_config = cfg
                        if token_request.provider:
                            break  # Exact match found
        if validator and token_request.provider:
            break  # Exact match found

    if not validator or not provider_config:
        raise HTTPException(
            status_code=503,
            detail=f"Provider '{token_request.provider}' not configured with valid discovery_url."
            if token_request.provider
            else "No provider configured with valid discovery_url.",
        )

    # Exchange the authorization code for tokens
    # Build token request data - support both PKCE and client_secret flows
    token_data = {
        "grant_type": "authorization_code",
        "code": token_request.code,
        "client_id": validator.client_id,
        "redirect_uri": token_request.redirect_uri,
    }

    # PKCE: include code_verifier if present
    if token_request.code_verifier:
        token_data["code_verifier"] = token_request.code_verifier

    # Traditional OAuth: include client_secret if present
    if provider_config.oauth_test_client_secret:
        token_data["client_secret"] = provider_config.oauth_test_client_secret

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                validator.oauth_test_token_endpoint,
                data=token_data,
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()

            token_data = response.json()

            # Log what tokens we received for debugging
            has_access = bool(token_data.get("access_token"))
            has_id = bool(token_data.get("id_token"))
            logging.info(
                f"Token exchange successful for {token_request.provider}: access_token={has_access}, id_token={has_id}"
            )

            # Return the token(s) exactly as provided by the OAuth provider
            return TokenResponse(
                access_token=token_data.get("access_token", ""),
                token_type=token_data.get("token_type", "Bearer"),
                expires_in=token_data.get("expires_in"),
                id_token=token_data.get("id_token"),
            )

        except httpx.HTTPStatusError as e:
            logging.error(
                f"Token exchange failed: {e.response.status_code} - {e.response.text}"
            )
            raise HTTPException(
                status_code=e.response.status_code,
                detail=f"Token exchange failed: {e.response.text}",
            )
        except Exception as e:
            logging.error(f"Token exchange error: {e}")
            raise HTTPException(
                status_code=500, detail=f"Token exchange failed: {str(e)}"
            )


@router.get("/oauth/config")
async def get_oauth_config(request: Request) -> dict:
    """Get OAuth configuration for the test frontend.

    This is a TEST/CONVENIENCE endpoint that returns config for oauth-test.html.
    Returns all enabled providers with OAuth test endpoints.
    """
    settings = request.app.state.settings

    # Check if OAuth test endpoints are enabled globally
    if not settings.oauth_test_enabled:
        return {
            "error": "OAuth test endpoints not enabled. Set oauth_test_enabled: true in config."
        }

    # Restrict to localhost when test endpoints are enabled
    _ensure_localhost(request)

    # Build redirect URI from actual request
    redirect_uri = f"{request.url.scheme}://{request.url.netloc}/static/oauth-test.html"

    # Collect all enabled providers with test authorization endpoints
    providers = []
    for validator in request.app.state.jwt_providers:
        if validator.oauth_test_authorization_endpoint:
            # Find matching config for scopes
            provider_scopes = ["openid", "email", "profile"]  # default
            for cfg in settings.jwt_providers:
                if cfg.enabled and cfg.name == validator.name:
                    provider_scopes = cfg.oauth_test_scopes
                    break

            providers.append(
                {
                    "name": validator.name,
                    "authorization_url": validator.oauth_test_authorization_endpoint,
                    "client_id": validator.client_id,
                    "scopes": " ".join(provider_scopes),
                }
            )

    if not providers:
        return {"error": "No provider with valid discovery_url configured."}

    return {
        "redirect_uri": redirect_uri,
        "providers": providers,
    }


# Developer-only JWT recording endpoint
if os.getenv("TOM_ENABLE_TEST_RECORDING", "").lower() == "true":
    logger.warning(
        "WARN:\t  TOM_ENABLE_TEST_RECORDING=true - this is a DEVELOPER ONLY feature"
    )

    @router.post("/dev/record-jwt")
    async def record_jwt_for_testing(request: Request):
        """DEVELOPER ONLY: Record a JWT for test fixtures.

        Set TOM_ENABLE_TEST_RECORDING=true to enable this endpoint.
        Send a valid JWT via Authorization header, and this will:
        1. Validate it (or record validation failure)
        2. Extract all claims
        3. Save to tests/fixtures/jwt/{provider}_{validity}_{timestamp}.yaml

        This endpoint accepts both valid and invalid tokens.
        Disabled in production by default.
        """
        # Restrict to localhost regardless of oauth_test_enabled flag
        _ensure_localhost(request)

        # Get raw token
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return {
                "error": "Missing or invalid Authorization header",
                "expected": "Authorization: Bearer <token>",
            }

        token = auth_header[7:]  # Remove "Bearer " prefix

        # Try to validate the token
        valid = False
        error = None
        provider = None
        user = None
        claims = None
        validator = None

        try:
            # Use the internal JWT auth function
            auth_result = await _jwt_auth(token, request.app.state.jwt_providers)
            valid = True
            provider = auth_result["provider"]
            user = auth_result["user"]
            claims = auth_result["claims"]

            # Find the validator that was used
            for v in request.app.state.jwt_providers:
                if v.name == provider:
                    validator = v
                    break
        except TomAuthException as e:
            error = str(e)
            # Try to extract provider from unverified token for filename
            try:
                unverified = jose_jwt.get_unverified_claims(token)
                issuer = unverified.get("iss", "unknown")
                # Try to match issuer to provider name
                for p in request.app.state.jwt_providers:
                    if p.issuer == issuer:
                        provider = p.name
                        validator = p
                        break
                if not provider:
                    provider = "unknown"
            except:
                provider = "unknown"

        # Create fixture structure
        fixture = {
            "description": f"Recorded from live {provider} token"
            if valid
            else f"Invalid token - {error}",
            "recorded_at": datetime.utcnow().isoformat() + "Z",
            "provider": provider,
            "jwt": token,
            "expected": {
                "valid": valid,
            },
        }

        # Add provider configuration used for validation
        if validator:
            fixture["provider_config"] = {
                "name": validator.name,
                "discovery_url": validator.discovery_url,
                "client_id": validator.client_id,
                "issuer": validator.issuer,
                "jwks_uri": validator.jwks_uri,
                "audience": validator.audience,
                "leeway_seconds": validator.leeway_seconds,
            }
            # Add tenant_id for Entra
            if hasattr(validator, "tenant_id") and validator.tenant_id:
                fixture["provider_config"]["tenant_id"] = validator.tenant_id

        # Add error if invalid
        if not valid:
            fixture["expected"]["error"] = error

        # Add claims and user info if valid
        if valid and claims is not None:
            fixture["expected"]["user"] = user
            fixture["expected"]["provider"] = provider
            fixture["expected"]["claims"] = claims

            # Add time information for expiration testing
            iat = claims.get("iat")
            if iat:
                fixture["validation_time"] = (
                    datetime.utcfromtimestamp(iat).isoformat() + "Z"
                )
            exp = claims.get("exp")
            if exp:
                fixture["expiration_time"] = (
                    datetime.utcfromtimestamp(exp).isoformat() + "Z"
                )

        # Create fixtures directory
        project_root = Path(request.app.state.settings.project_root)
        fixtures_dir = project_root / "tests" / "fixtures" / "jwt"
        fixtures_dir.mkdir(parents=True, exist_ok=True)

        # Create filename
        timestamp = int(datetime.utcnow().timestamp())
        validity = "valid" if valid else "invalid"
        filename = f"{provider}_{validity}_{timestamp}.yaml"
        filepath = fixtures_dir / filename

        # Save fixture
        with open(filepath, "w") as f:
            yaml.dump(fixture, f, default_flow_style=False, sort_keys=False)

        return {
            "message": "JWT fixture recorded",
            "file": str(filepath.relative_to(project_root)),
            "valid": valid,
            "provider": provider,
            "user": user if valid else None,
        }
