"""Base JWT validator with common validation logic."""

import json
import logging
import time
from typing import Optional, Dict, Any

import httpx
from jose import jwt, jwk
from jose.exceptions import JWTError, ExpiredSignatureError, JWTClaimsError
from jose.constants import ALGORITHMS

from tom_controller.exceptions import (
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
        self.issuer = provider_config.get("issuer")
        self.audience = provider_config.get("audience")
        self.client_id = provider_config.get("client_id")
        self.jwks_uri = provider_config.get("jwks_uri")
        self.leeway_seconds = provider_config.get("leeway_seconds", 30)

        # Cache for JWKS keys
        self._jwks_cache: Optional[Dict[str, Any]] = None
        self._jwks_cache_time: float = 0
        self._jwks_cache_ttl: int = 3600  # Cache for 1 hour

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

    async def fetch_jwks(self) -> Dict[str, Any]:
        """Fetch JWKS from the provider's JWKS URI.

        Returns:
            Dictionary containing JWKS data

        Raises:
            JWKSFetchError: If fetching JWKS fails
        """
        if not self.jwks_uri:
            raise JWKSFetchError(f"No JWKS URI configured for {self.name}")

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
        try:
            # Get the signing key
            signing_key = await self.get_signing_key(token)

            # Convert JWK to RSA key
            rsa_key = jwk.construct(signing_key)

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
                "leeway": self.leeway_seconds,  # leeway goes in options dict
            }

            # Build kwargs for decode
            decode_kwargs = {
                "algorithms": [ALGORITHMS.RS256],
                "audience": self._get_validation_audience(),
                "issuer": self.issuer,
                "options": options,
            }

            # Add access_token if provided for at_hash validation
            if access_token:
                decode_kwargs["access_token"] = access_token

            claims = jwt.decode(
                token,
                rsa_key,
                **decode_kwargs
            )

            # Additional validation
            self._validate_claims(claims)

            logger.info(
                f"Successfully validated JWT from {self.name} for user: {claims.get('sub')}"
            )
            return claims

        except ExpiredSignatureError as e:
            logger.warning(f"Token expired: {e}")
            raise JWTExpiredError(f"Token has expired: {e}")
        except JWTClaimsError as e:
            logger.warning(f"Invalid claims: {e}")
            raise JWTInvalidClaimsError(f"Invalid token claims: {e}")
        except JWTError as e:
            logger.warning(f"JWT validation failed: {e}")
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
