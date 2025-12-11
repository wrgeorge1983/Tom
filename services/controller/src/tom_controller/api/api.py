import logging
import os
import yaml
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Request, Query, HTTPException, Response
import httpx
from jose import jwt as jose_jwt
from pydantic import BaseModel
import saq

from tom_controller.api.auth import AuthResponse, _jwt_auth, do_auth
from tom_controller.api.models import (
    JobResponse,
)
from tom_controller.monitoring import MetricsExporter

from tom_controller.exceptions import (
    TomException,
    TomAuthException,
)
from tom_controller.parsing import parse_output

logger = logging.getLogger(__name__)


class AuthRouter(APIRouter):
    auth_dep = Depends(do_auth)

    def __init__(self, *args, **kwargs):
        default_dependencies = kwargs.get("dependencies", [])
        kwargs["dependencies"] = [self.auth_dep] + default_dependencies
        super().__init__(*args, **kwargs)


api_router = AuthRouter()

# Unauthenticated router for Prometheus metrics
prometheus_router = APIRouter()


@api_router.get("/")
async def root():
    return {"message": "Hello World"}


@api_router.get("/job/{job_id}")
async def job(
    request: Request,
    job_id: str,
    parse: bool = Query(False, description="Parse output using TextFSM"),
    parser: str = Query("textfsm", description="Parser to use"),
    template: Optional[str] = Query(None, description="Template name for parsing"),
    include_raw: bool = Query(False, description="Include raw output with parsed"),
) -> Optional[JobResponse | dict]:
    queue: saq.Queue = request.app.state.queue
    job_response = await JobResponse.from_job_id(job_id, queue)

    # Log job status check
    if job_response.status == "NEW":
        logger.debug(f"Job {job_id} not found or NEW")
        return None
    elif job_response.status == "COMPLETE":
        logger.info(
            f"Job {job_id} status check: COMPLETE after {job_response.attempts} attempt(s)"
        )
    elif job_response.status == "FAILED":
        # Extract error summary
        error_summary = None
        if job_response.error:
            if "AuthenticationException" in job_response.error:
                error_summary = "Authentication failed"
            elif "GatingException" in job_response.error:
                error_summary = "Device busy"
            else:
                error_lines = job_response.error.strip().split("\n")
                if error_lines:
                    error_summary = error_lines[-1][:200]
        logger.error(
            f"Job {job_id} status check: FAILED after {job_response.attempts} attempt(s) - {error_summary or 'Unknown error'}"
        )
    else:
        logger.info(f"Job {job_id} status check: {job_response.status}")

    # If parsing requested and job is complete with results
    if parse and job_response.status == "COMPLETE" and job_response.result:
        settings = request.app.state.settings

        # Extract device_type and commands from metadata
        device_type = None
        commands = None
        if job_response.metadata:
            device_type = job_response.metadata.get("device_type")
            commands = job_response.metadata.get("commands", [])

        # Parse each command result
        parsed_results = {}
        command_data = job_response.command_data
        if command_data:
            for command, raw_output in command_data.items():
                if isinstance(raw_output, str):
                    parsed_results[command] = parse_output(
                        raw_output=raw_output,
                        settings=settings,
                        device_type=device_type,
                        command=command,
                        template=template,
                        include_raw=include_raw,
                        parser_type=parser,
                    )
                else:
                    parsed_results[command] = raw_output
        else:
            # Single result, not a dict
            parsed_results = parse_output(
                raw_output=str(job_response.result),
                settings=settings,
                device_type=device_type,
                command=commands[0] if commands else None,
                template=template,
                include_raw=include_raw,
                parser_type=parser,
            )

        return parsed_results

    return job_response


@prometheus_router.get("/metrics")
async def metrics(request: Request) -> Response:
    """Prometheus metrics endpoint (unauthenticated for Prometheus scraping).

    This endpoint is scraped by Prometheus to collect metrics.
    Metrics are collected fresh from Redis on each scrape (stateless).

    Note: This endpoint is intentionally unauthenticated to allow Prometheus
    to scrape metrics without authentication. Metrics contain only aggregated
    statistics with no sensitive details.
    """
    # Get Redis client from app state
    redis_client = request.app.state.redis_client

    # Create exporter and generate metrics
    exporter = MetricsExporter(redis_client)
    metrics_output = await exporter.generate_metrics()

    return Response(content=metrics_output, media_type="text/plain")


@api_router.get("/auth/debug")
async def debug_auth(auth: AuthResponse = Depends(do_auth)) -> dict:
    """Debug endpoint to see all authentication details including custom claims."""
    return {
        "method": auth["method"],
        "user": auth["user"],
        "provider": auth["provider"],
        "all_claims": auth.get(
            "claims", {}
        ),  # This will show ALL claims from the token
        "custom_claims": {
            k: v
            for k, v in auth.get("claims", {}).items()
            if k
            not in [
                "iss",
                "sub",
                "aud",
                "exp",
                "iat",
                "nbf",
                "jti",
                "at_hash",
                "nonce",
                "auth_time",
            ]
        },  # Filter to show only custom/non-standard claims
    }


@api_router.get("/userinfo")
async def get_userinfo(
    request: Request,
    access_token: str = Query(
        ..., description="OAuth access token to use for userinfo request"
    ),
    provider: Optional[str] = Query(
        None, description="Provider name (auto-detected from auth if not specified)"
    ),
    auth: AuthResponse = Depends(do_auth),
) -> dict:
    """Get user information from OIDC provider using the access token.

    This is a convenience/test endpoint. In production, clients should call
    the provider's userinfo endpoint directly.

    Note: Requires an access token, not an ID token. Access tokens are used
    for accessing resources, while ID tokens are used for authentication.
    """
    # Must be authenticated with JWT
    if auth["method"] != "jwt":
        raise TomAuthException("User info only available for JWT authentication")

    # Find the validator instance
    settings = request.app.state.settings
    validator = None

    # Use provider from query param, or fall back to authenticated provider
    target_provider = provider or auth["provider"]

    for v in request.app.state.jwt_providers:
        if v.name == target_provider:
            validator = v
            break

    if not validator:
        raise TomException(f"Provider {target_provider} not found")

    # Check if OAuth test endpoints are enabled globally
    if not settings.oauth_test_enabled:
        raise TomException(
            "OAuth test endpoints not enabled. Set oauth_test_enabled: true in config."
        )

    # Restrict to localhost when test endpoints are enabled
    _ensure_localhost(request)

    if not validator.oauth_test_userinfo_endpoint:
        raise TomException(
            f"Userinfo endpoint not available for provider {target_provider} - ensure discovery_url is configured"
        )

    # Call the OIDC userinfo endpoint with the access token
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                validator.oauth_test_userinfo_endpoint,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            response.raise_for_status()

            user_info = response.json()

            # Add provider info
            user_info["_provider"] = target_provider
            user_info["_auth_method"] = auth["method"]

            return user_info

        except httpx.HTTPStatusError as e:
            logging.error(
                f"Failed to get user info: {e.response.status_code} - {e.response.text}"
            )
            raise TomException(
                f"Failed to get user info from provider: {e.response.text}"
            )
        except Exception as e:
            logging.error(f"Error getting user info: {e}")
            raise TomException(f"Failed to get user info: {str(e)}")


# OAuth endpoints (not requiring authentication)
oauth_test_router = APIRouter()


def _ensure_localhost(request: Request):
    host = request.client.host if request.client else None
    if host not in {"127.0.0.1", "::1", "localhost"}:
        # Some proxies may set X-Forwarded-For; we intentionally keep this strict
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


@oauth_test_router.post("/oauth/token")
async def exchange_token(
    request: Request, token_request: TokenRequest
) -> TokenResponse:
    """Exchange OAuth authorization code for JWT token.

    This is a TEST/CONVENIENCE endpoint. In production, clients should handle
    OAuth flows themselves and only send validated JWTs to Tom.
    """
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


@oauth_test_router.get("/oauth/config")
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


if os.getenv("TOM_ENABLE_TEST_RECORDING", "").lower() == "true":
    logger.warning(
        "WARN:\t  TOM_ENABLE_TEST_RECORDING=true - this is a DEVELOPER ONLY feature"
    )

    @oauth_test_router.post("/dev/record-jwt")
    async def record_jwt_for_testing(request: Request):
        # Restrict to localhost regardless of oauth_test_enabled flag
        _ensure_localhost(request)
        """
        DEVELOPER ONLY: Record a JWT for test fixtures.
        
        Set TOM_ENABLE_TEST_RECORDING=true to enable this endpoint.
        Send a valid JWT via Authorization header, and this will:
        1. Validate it (or record validation failure)
        2. Extract all claims
        3. Save to tests/fixtures/jwt/{provider}_{validity}_{timestamp}.yaml
        
        This endpoint accepts both valid and invalid tokens.
        Disabled in production by default.
        """

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


# Include sub-routers
from tom_controller.api import raw, device, inventory, templates

api_router.include_router(raw.router)
api_router.include_router(device.router)
api_router.include_router(inventory.router)
api_router.include_router(templates.router)
