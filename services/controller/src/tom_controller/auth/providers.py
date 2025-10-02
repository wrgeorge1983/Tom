"""Provider-specific JWT validators.

Provider Status:
- Duo Security: ✅ TESTED AND WORKING
- Google OAuth: ⚠️ SPECULATIVE/UNTESTED (should work, based on OIDC standards)
- GitHub Apps: ⚠️ SPECULATIVE/UNTESTED (may need significant work)
- Microsoft Entra ID: ⚠️ SPECULATIVE/UNTESTED (should work, based on OIDC standards)
"""

import logging
from pathlib import Path
from typing import Dict, Any, Optional

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend
from jose import jwt, jwk
from jose.constants import ALGORITHMS

from .jwt_validator import JWTValidator
from tom_controller.exceptions import JWTValidationError, JWTInvalidClaimsError


logger = logging.getLogger(__name__)


class DuoJWTValidator(JWTValidator):
    """Duo Security JWT validator.
    
    ✅ TESTED AND WORKING with Duo PKCE flow.
    """

    def __init__(self, provider_config: Dict[str, Any]):
        super().__init__(provider_config)
        # Duo-specific initialization if needed

    def _validate_claims(self, claims: Dict[str, Any]):
        """Validate Duo-specific claims."""
        super()._validate_claims(claims)

        # Duo-specific validation
        # Access tokens only have 'sub', while ID tokens have email/name
        # Both are valid - access tokens are for API access, ID tokens for identity
        # No additional validation needed beyond base class checks

    def get_user_identifier(self, claims: Dict[str, Any]) -> str:
        """Extract user identifier from Duo claims."""
        # Duo typically uses preferred_username or email
        return (
            claims.get("preferred_username")
            or claims.get("email")
            or claims.get("sub", "unknown")
        )


class GoogleJWTValidator(JWTValidator):
    """Google OAuth JWT validator.
    
    ⚠️ SPECULATIVE IMPLEMENTATION - UNTESTED
    
    Based on standard OIDC, should work but needs testing with real Google tokens.
    """

    def __init__(self, provider_config: Dict[str, Any]):
        super().__init__(provider_config)
        # Google's well-known JWKS URI if not provided
        if not self.jwks_uri:
            self.jwks_uri = "https://www.googleapis.com/oauth2/v3/certs"

        # Google typically uses issuer accounts.google.com or https://accounts.google.com
        if not self.issuer:
            self.issuer = "https://accounts.google.com"

    def _validate_claims(self, claims: Dict[str, Any]):
        """Validate Google-specific claims."""
        super()._validate_claims(claims)

        # Google-specific validation
        if "email" not in claims:
            raise JWTInvalidClaimsError("Missing email claim in Google token")

        # Optionally verify email is verified
        if not claims.get("email_verified", False):
            logger.warning(f"Email not verified for Google user: {claims.get('email')}")

    def get_user_identifier(self, claims: Dict[str, Any]) -> str:
        """Extract user identifier from Google claims."""
        return claims.get("email", claims.get("sub", "unknown"))


class GitHubJWTValidator(JWTValidator):
    """GitHub App JWT validator.

    GitHub uses app-specific signing with private keys rather than JWKS.
    """

    def __init__(self, provider_config: Dict[str, Any]):
        super().__init__(provider_config)
        self.app_id = provider_config.get("app_id")
        self.private_key_path = provider_config.get("private_key_path")
        self._private_key = None

        if self.private_key_path:
            self._load_private_key()

    def _load_private_key(self):
        """Load GitHub App private key from file."""
        if not self.private_key_path:
            raise JWTValidationError("GitHub App private key path not configured")
            
        try:
            key_path = Path(self.private_key_path)
            if not key_path.exists():
                raise JWTValidationError(
                    f"GitHub App private key not found: {self.private_key_path}"
                )

            with open(key_path, "rb") as key_file:
                self._private_key = serialization.load_pem_private_key(
                    key_file.read(), password=None, backend=default_backend()
                )
            logger.info(f"Loaded GitHub App private key from {self.private_key_path}")
        except Exception as e:
            logger.error(f"Failed to load GitHub App private key: {e}")
            raise JWTValidationError(f"Failed to load GitHub App private key: {e}")

    async def validate_token(self, token: str, access_token: Optional[str] = None) -> Dict[str, Any]:
        """Validate GitHub JWT token.

        GitHub tokens are typically validated differently than standard OIDC tokens.
        This is a simplified implementation - actual GitHub App authentication
        may require additional steps.
        
        NOTE: This is UNTESTED and may need significant changes for real GitHub integration.
        """
        if not self._private_key:
            raise JWTValidationError("GitHub App private key not configured")

        try:
            from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
            
            public_key_pem = self._private_key.public_key().public_bytes(
                encoding=Encoding.PEM,
                format=PublicFormat.SubjectPublicKeyInfo
            )
            
            claims = jwt.decode(
                token,
                public_key_pem,
                algorithms=[ALGORITHMS.RS256],
                options={
                    "verify_signature": True,
                    "verify_exp": True,
                    "require_exp": True,
                },
            )

            self._validate_claims(claims)
            return claims

        except Exception as e:
            logger.error(f"GitHub JWT validation failed: {e}")
            raise JWTValidationError(f"GitHub token validation failed: {e}")

    def _validate_claims(self, claims: Dict[str, Any]):
        """Validate GitHub-specific claims."""
        super()._validate_claims(claims)

        # GitHub-specific validation
        # GitHub tokens might have different claim structures
        pass

    def get_user_identifier(self, claims: Dict[str, Any]) -> str:
        """Extract user identifier from GitHub claims."""
        # GitHub might use login, email, or sub
        return (
            claims.get("login") or claims.get("email") or claims.get("sub", "unknown")
        )


class EntraJWTValidator(JWTValidator):
    """Microsoft Entra ID (formerly Azure AD) JWT validator.
    
    ⚠️ SPECULATIVE IMPLEMENTATION - UNTESTED
    
    Based on standard OIDC, should work but needs testing with real Entra ID tokens.
    """

    def __init__(self, provider_config: Dict[str, Any]):
        super().__init__(provider_config)
        self.tenant_id = provider_config.get("tenant_id")

        # Build Entra ID URIs if not provided
        if not self.jwks_uri and self.tenant_id:
            self.jwks_uri = f"https://login.microsoftonline.com/{self.tenant_id}/discovery/v2.0/keys"

        if not self.issuer and self.tenant_id:
            # Entra ID can have multiple issuer formats
            self.issuer = f"https://login.microsoftonline.com/{self.tenant_id}/v2.0"

    def _validate_claims(self, claims: Dict[str, Any]):
        """Validate Entra ID-specific claims."""
        super()._validate_claims(claims)

        # Entra ID specific validation
        # Check for tenant ID in token if configured
        if self.tenant_id:
            token_tid = claims.get("tid")
            if token_tid and token_tid != self.tenant_id:
                raise JWTInvalidClaimsError(
                    f"Token tenant ID {token_tid} doesn't match configured tenant {self.tenant_id}"
                )

    def get_user_identifier(self, claims: Dict[str, Any]) -> str:
        """Extract user identifier from Entra ID claims."""
        # Entra ID uses upn (User Principal Name) or email
        return (
            claims.get("preferred_username")
            or claims.get("upn")
            or claims.get("email")
            or claims.get("sub", "unknown")
        )


def get_jwt_validator(provider_config: Dict[str, Any]) -> JWTValidator:
    """Factory function to get the appropriate JWT validator for a provider.

    Args:
        provider_config: Provider configuration dictionary

    Returns:
        JWTValidator instance for the specified provider

    Raises:
        ValueError: If provider type is unknown
    """
    provider_name = provider_config.get("name", "").lower()

    validators = {
        "duo": DuoJWTValidator,
        "google": GoogleJWTValidator,
        "github": GitHubJWTValidator,
        "entra": EntraJWTValidator,
        "azure": EntraJWTValidator,  # Alias for Entra
        "azuread": EntraJWTValidator,  # Another alias
    }

    validator_class = validators.get(provider_name)
    if not validator_class:
        raise ValueError(f"Unknown JWT provider: {provider_name}")

    logger.info(f"Creating {provider_name} JWT validator")
    return validator_class(provider_config)
