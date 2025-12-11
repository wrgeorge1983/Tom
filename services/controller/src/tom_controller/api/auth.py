import logging
from typing import TypedDict, Literal, Optional, Dict, Any

from jose import jwt as jose_jwt, JWTError
from starlette.requests import Request

from tom_controller.auth import JWTValidator
from tom_controller.config import settings as app_settings

from tom_controller.exceptions import TomAuthException, JWTValidationError, TomAuthorizationException, TomException


class AuthResponse(TypedDict):
    method: Literal["api_key", "jwt", "none"]
    user: str | None
    provider: Optional[str]
    claims: Optional[Dict[str, Any]]


def api_key_auth(request: Request) -> AuthResponse:
    valid_headers = request.app.state.settings.api_key_headers
    valid_api_keys = request.app.state.settings.api_key_users

    for header in valid_headers:
        api_key = request.headers.get(header)
        if api_key in valid_api_keys:
            return {
                "method": "api_key",
                "user": valid_api_keys[api_key],
                "provider": None,
                "claims": None,
            }

    header_keys = ", ".join(f"'{header}'" for header in valid_headers)

    raise TomAuthException(
        f"Missing or invalid API key. Requires one of these headers: {header_keys}"
    )


async def _jwt_auth(token: str, providers: list[JWTValidator]) -> AuthResponse:
    """Validate JWT against providers in order."""

    import re

    token_issuer = None

    try:
        unverified_claims = jose_jwt.get_unverified_claims(token)
        token_issuer = unverified_claims.get("iss")
        oauth_provider = next(
            provider for provider in providers if provider.issuer == token_issuer
        )
    except JWTError as e:
        logging.error(f"JWT validation failed: {e}")
        raise TomAuthException("Invalid JWT token - could not extract issuer") from e
    except StopIteration:
        logging.error(f"No matching provider found for issuer: {token_issuer}")
        raise TomAuthException("Invalid JWT token - issuer not found")

    logging.info(f"Token issuer (unverified): {token_issuer}")

    try:
        claims = await oauth_provider.validate_token(token)
        user = oauth_provider.get_user_identifier(claims)
    except JWTValidationError as e:
        logging.warning(
            f"JWT validation failed for provider {oauth_provider.name}: {e}"
        )
        raise TomAuthException("Invalid JWT token - could not validate token") from e
    finally:
        await oauth_provider.close()

    # Enforce simple allow policy for JWT-authenticated users.
    # Precedence: allowed_users > allowed_domains > allowed_user_regex
    allowed_users = [u.lower() for u in app_settings.allowed_users]
    allowed_domains = [d.lower() for d in app_settings.allowed_domains]
    allowed_user_regex = app_settings.allowed_user_regex or []

    if allowed_users or allowed_domains or allowed_user_regex:
        canonical_user = (user or "").lower()

        # 1) Exact user allowlist
        if allowed_users and canonical_user in allowed_users:
            pass  # allowed
        else:
            # Determine email-like identifier for domain matching
            email_like = None
            for k in ("email", "preferred_username", "upn"):
                v = claims.get(k)
                if isinstance(v, str) and "@" in v:
                    email_like = v
                    break

            # 2) Domain allowlist
            domain_ok = False
            if allowed_domains and email_like:
                domain = email_like.split("@")[-1].lower()
                domain_ok = domain in allowed_domains

            if not domain_ok:
                # 3) Regex against canonical user, then email if present
                regex_ok = False
                if allowed_user_regex:
                    regex_ok = any(
                        re.search(p, canonical_user, flags=re.IGNORECASE)
                        for p in allowed_user_regex
                    ) or (
                        isinstance(email_like, str)
                        and any(
                            re.search(p, email_like, flags=re.IGNORECASE)
                            for p in allowed_user_regex
                        )
                    )

                if not regex_ok:
                    raise TomAuthorizationException(
                        f"Access denied: {canonical_user=} not permitted by policy"
                    )

    if app_settings.permit_logging_user_details:
        logging.info(
            f"JWT successfully validated by {oauth_provider.name} for user {user}"
        )
    else:
        logging.info(f"JWT successfully validated by {oauth_provider.name}")

    return {
        "method": "jwt",
        "user": user,
        "provider": oauth_provider.name,
        "claims": claims,
    }


async def jwt_auth(request: Request) -> AuthResponse:
    """Validate JWT from Authorization header."""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise TomAuthException("Missing or invalid Bearer token")

    token = auth_header[7:]  # Remove "Bearer " prefix

    # Debug: Log token prefix only when PII logging is permitted
    if app_settings.permit_logging_user_details:
        logging.info(f"Attempting JWT validation with token starting: {token[:50]}...")
    else:
        logging.info("Attempting JWT validation")

    # Check HTTPS requirement
    settings = request.app.state.settings
    if settings.jwt_require_https:
        # Check if connection is secure
        if request.url.scheme != "https":
            # Allow localhost for development
            if request.client and request.client.host not in [
                "127.0.0.1",
                "localhost",
                "::1",
            ]:
                raise TomAuthException("JWT authentication requires HTTPS")

    return await _jwt_auth(token, request.app.state.jwt_providers)


async def do_auth(request: Request) -> AuthResponse:
    settings = request.app.state.settings

    # Debug logging
    logging.info(f"Auth check - auth_mode: {settings.auth_mode}")

    if settings.auth_mode == "none":
        return {"method": "none", "user": None, "provider": None, "claims": None}

    # Try API key auth first in hybrid mode
    if settings.auth_mode in ["api_key", "hybrid"]:
        try:
            return api_key_auth(request)

        except TomAuthException:
            if settings.auth_mode == "api_key":
                raise
            # Continue to JWT check in hybrid mode

    # Try JWT auth
    if settings.auth_mode in ["jwt", "hybrid"]:
        return await jwt_auth(request)

    raise TomException(f"Unknown auth mode {settings.auth_mode}")
