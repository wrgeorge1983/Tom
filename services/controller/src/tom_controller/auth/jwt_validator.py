"""Base JWT validator with common validation logic."""

import json
import logging
import time
from typing import Optional, Dict, Any

import httpx
from jose import jwt, jwk
from jose.exceptions import JWTError, ExpiredSignatureError, JWTClaimsError
from jose.constants import ALGORITHMS

from tom_controller.config import settings as app_settings
from tom_controller.exceptions import (
    TomException,
    JWTValidationError,
    JWTExpiredError,
    JWTInvalidSignatureError,
    JWTInvalidClaimsError,
    JWKSFetchError,
)


logger = logging.getLogger(__name__)


class JWTValidator:
    """Base class for JWT validation with common logic."""

    def __init__(self, provider_config: Dict[str, Any]):
        """Initialize JWT validator with provider configuration.

        Args:
            provider_config: Provider-specific configuration dictionary
        """
        self.config = provider_config
        self.name = provider_config.get("name", "unknown")
        self.discovery_url = provider_config["discovery_url"]  # Required
        self.audience = provider_config.get("audience")
        self.client_id = provider_config["client_id"]  # Required
        self.leeway_seconds = provider_config.get("leeway_seconds", 30)

        # Populated from OIDC discovery
        self.issuer: Optional[str] = None
        self.jwks_uri: Optional[str] = None
        
        # OAuth test endpoint URLs (populated from OIDC discovery)
        self.oauth_test_authorization_endpoint: Optional[str] = None
        self.oauth_test_token_endpoint: Optional[str] = None
        self.oauth_test_userinfo_endpoint: Optional[str] = None

        # Cache for JWKS keys
        self._jwks_cache: Optional[Dict[str, Any]] = None
        self._jwks_cache_time: float = 0
        self._jwks_cache_ttl: int = 3600  # Cache for 1 hour
        
        # Discovery cache
        self._discovery_cache: Optional[Dict[str, Any]] = None
        self._discovery_initialized: bool = False

        # HTTP client for fetching JWKS
        self._http_client: Optional[httpx.AsyncClient] = None

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=30.0)
        return self._http_client

    async def close(self):
        """Clean up resources."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    async def _ensure_discovery(self):
        """Perform OIDC discovery to populate issuer, jwks_uri, and OAuth endpoints."""
        if self._discovery_initialized:
            return
            
        logger.info(f"Performing OIDC discovery for {self.name} from {self.discovery_url}")
        
        from .oidc_discovery import OIDCDiscovery
        
        discovery = OIDCDiscovery(self.discovery_url)
        doc = await discovery.discover()
        await discovery.close()
        
        # Populate from discovered values
        self.issuer = doc.get("issuer")
        self.jwks_uri = doc.get("jwks_uri")
        
        if not self.issuer or not self.jwks_uri:
            raise TomException(
                f"OIDC discovery for {self.name} did not return required fields. "
                f"Got issuer={self.issuer}, jwks_uri={self.jwks_uri}"
            )
        
        logger.info(f"Discovered issuer: {self.issuer}")
        logger.info(f"Discovered jwks_uri: {self.jwks_uri}")
        
        # Populate OAuth test endpoints
        self.oauth_test_authorization_endpoint = doc.get("authorization_endpoint")
        self.oauth_test_token_endpoint = doc.get("token_endpoint")
        self.oauth_test_userinfo_endpoint = doc.get("userinfo_endpoint")
        
        logger.debug(f"Discovered OAuth endpoints - auth: {self.oauth_test_authorization_endpoint}, "
                   f"token: {self.oauth_test_token_endpoint}, userinfo: {self.oauth_test_userinfo_endpoint}")
        
        self._discovery_cache = doc
        self._discovery_initialized = True

    async def fetch_jwks(self) -> Dict[str, Any]:
        """Fetch JWKS from the provider's JWKS URI.

        Returns:
            Dictionary containing JWKS data

        Raises:
            JWKSFetchError: If fetching JWKS fails
        """
        # Try discovery first if configured
        await self._ensure_discovery()
        
        if not self.jwks_uri:
            if self.discovery_url:
                raise JWKSFetchError(f"OIDC discovery failed to find jwks_uri for {self.name}")
            else:
                raise JWKSFetchError(f"No JWKS URI configured for {self.name}. Either provide 'jwks_uri' or 'discovery_url' in config.")

        # Check cache
        now = time.time()
        if self._jwks_cache and (now - self._jwks_cache_time) < self._jwks_cache_ttl:
            logger.debug(f"Using cached JWKS for {self.name}")
            return self._jwks_cache

        logger.info(f"Fetching JWKS from {self.jwks_uri}")
        try:
            client = await self._get_http_client()
            response = await client.get(self.jwks_uri)
            response.raise_for_status()
            jwks_data = response.json()

            # Update cache
            self._jwks_cache = jwks_data
            self._jwks_cache_time = now

            return jwks_data
        except Exception as e:
            logger.error(f"Failed to fetch JWKS from {self.jwks_uri}: {e}")
            raise JWKSFetchError(f"Failed to fetch JWKS: {e}")

    async def get_signing_key(self, token: str) -> Dict[str, Any]:
        """Get the public key for token verification.

        Args:
            token: JWT token string

        Returns:
            Dictionary containing the signing key

        Raises:
            JWTValidationError: If key cannot be found
        """
        try:
            # Decode header without verification to get kid
            unverified_header = jwt.get_unverified_header(token)
            kid = unverified_header.get("kid")

            if not kid:
                raise JWTValidationError("No kid found in token header")

            # Fetch JWKS
            jwks_data = await self.fetch_jwks()

            # Find the key with matching kid
            for key in jwks_data.get("keys", []):
                if key.get("kid") == kid:
                    return key

            raise JWTValidationError(f"Unable to find key with kid: {kid}")

        except JWTError as e:
            logger.error(f"Error decoding token header: {e}")
            raise JWTValidationError(f"Invalid token format: {e}")

    def _get_validation_audience(self) -> Optional[str]:
        """Get the audience value to validate against.

        Returns the configured audience, or client_id as fallback.
        """
        return self.audience or self.client_id

    async def validate_token(self, token: str, access_token: Optional[str] = None) -> Dict[str, Any]:
        """Validate JWT and return claims.

        Args:
            token: JWT token string (typically an ID token)
            access_token: Optional access token for at_hash validation

        Returns:
            Dictionary containing validated claims

        Raises:
            JWTValidationError: If validation fails
            JWTExpiredError: If token has expired
            JWTInvalidSignatureError: If signature is invalid
            JWTInvalidClaimsError: If claims are invalid
        """
        # Ensure discovery has been performed if configured
        await self._ensure_discovery()
        
        try:
            # Basic validation start log without PII by default
            if app_settings.permit_logging_user_details:
                logger.info(f"Validating token (first 100 chars): {token[:100]}...")

            else:
                logger.info("Validating token")

            # Get unverified claims to log what we're working with (may include PII)
            try:
                unverified_claims = jwt.get_unverified_claims(token)
                logger.info(
                    f"Token unverified claims - iss: {unverified_claims.get('iss')}, aud: {unverified_claims.get('aud')}, exp: {unverified_claims.get('exp')}"
                )
            except Exception as e:
                logger.warning(f"Could not decode unverified claims: {e}")

            # Get the signing key
            signing_key = await self.get_signing_key(token)

            # Filter out non-standard JWK fields that some providers add
            standard_jwk_fields = {'kty', 'use', 'kid', 'x5t', 'n', 'e', 'alg', 'crv', 'x', 'y', 'd', 'p', 'q', 'dp', 'dq', 'qi', 'k'}
            filtered_key = {k: v for k, v in signing_key.items() if k in standard_jwk_fields}
            
            # Ensure alg is set for jwk.construct
            if 'alg' not in filtered_key and 'kty' in filtered_key:
                if filtered_key['kty'] == 'RSA':
                    filtered_key['alg'] = 'RS256'
                elif filtered_key['kty'] == 'EC':
                    filtered_key['alg'] = 'ES256'
            
            logger.debug(f"Filtered JWK key fields: {list(filtered_key.keys())}, kid: {filtered_key.get('kid')}")

            # Convert JWK to RSA key
            rsa_key = jwk.construct(filtered_key)
            
            # Log validation parameters
            logger.debug(f"Validating with audience={self._get_validation_audience()}, issuer={self.issuer}")

            # Determine allowed algorithm(s) based on token header and discovery doc
            header = jwt.get_unverified_header(token)
            header_alg = header.get("alg")
            if not header_alg:
                raise JWTValidationError("No alg found in token header")

            # Trust discovery when available
            allowed_from_discovery = None
            if self._discovery_cache:
                allowed_from_discovery = self._discovery_cache.get("id_token_signing_alg_values_supported")

            if allowed_from_discovery is not None:
                if header_alg not in allowed_from_discovery:
                    raise JWTInvalidClaimsError(
                        f"Token alg '{header_alg}' not allowed by provider (supported: {allowed_from_discovery})"
                    )
                algorithms = [header_alg]
            else:
                # Fall back to allowing only the header alg (assumed safe set handled by provider)
                algorithms = [header_alg]

            # Decode and validate the token
            options = {
                "verify_signature": True,
                "verify_exp": True,
                "verify_nbf": True,
                "verify_iat": True,
                "verify_aud": bool(self._get_validation_audience()),
                "verify_at_hash": bool(access_token),  # Verify at_hash if access_token provided
                "require_exp": True,
                "require_iat": True,
                "leeway": self.leeway_seconds,
            }

            # Build kwargs for decode
            decode_kwargs = {
                "algorithms": algorithms,
                "audience": self._get_validation_audience(),
                "issuer": self.issuer,
                "options": options,
            }

            # Add access_token if provided for at_hash validation
            if access_token:
                decode_kwargs["access_token"] = access_token

            logger.debug(f"Calling jwt.decode with: algorithms={decode_kwargs.get('algorithms')}, audience={decode_kwargs.get('audience')}, issuer={decode_kwargs.get('issuer')}")
            
            claims = jwt.decode(
                token,
                rsa_key,
                **decode_kwargs
            )

            # Additional validation
            self._validate_claims(claims)

            if app_settings.permit_logging_user_details:
                user_ident = self.get_user_identifier(claims)
                # If the identifier is just an opaque subject, shorten for logging clarity
                display_user = user_ident
                sub = claims.get("sub")
                if isinstance(sub, str) and user_ident == sub and len(sub) >= 24:
                    display_user = f"sub:{sub[:8]}\u2026"
                logger.info(
                    f"Successfully validated JWT from {self.name} for user: {display_user}"
                )
            else:
                logger.info(f"Successfully validated JWT from {self.name}")
            return claims

        except ExpiredSignatureError as e:
            logger.warning(f"Token expired: {e}")
            raise JWTExpiredError(f"Token has expired: {e}")
        except JWTClaimsError as e:
            logger.warning(f"Invalid claims: {e}")
            raise JWTInvalidClaimsError(f"Invalid token claims: {e}")
        except JWTError as e:
            logger.warning(f"JWT validation failed: {e}")
            logger.debug(f"Token validation failed with params: aud={self._get_validation_audience()}, iss={self.issuer}, alg=RS256")
            raise JWTInvalidSignatureError(f"Invalid token signature: {e}")
        except Exception as e:
            logger.error(f"Unexpected error during JWT validation: {e}")
            raise JWTValidationError(f"Token validation failed: {e}")

    def _validate_claims(self, claims: Dict[str, Any]):
        """Perform additional claim validation.

        Override in subclasses for provider-specific validation.

        Args:
            claims: Decoded JWT claims

        Raises:
            JWTInvalidClaimsError: If claims are invalid
        """
        # Base implementation - check for required claims
        required_claims = ["sub", "iat", "exp"]
        missing_claims = [claim for claim in required_claims if claim not in claims]

        if missing_claims:
            raise JWTInvalidClaimsError(f"Missing required claims: {missing_claims}")

    def get_user_identifier(self, claims: Dict[str, Any]) -> str:
        """Extract user identifier from claims.

        Override in subclasses for provider-specific logic.

        Args:
            claims: Validated JWT claims

        Returns:
            User identifier string
        """
        # Try common claim names for user identification
        return (
            claims.get("email")
            or claims.get("preferred_username")
            or claims.get("sub", "unknown")
        )
