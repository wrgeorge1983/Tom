"""Provider-specific JWT validators.

Provider Status:
- Duo Security: ✅ TESTED AND WORKING (ID tokens and access tokens)
- Google OAuth: ✅ TESTED AND WORKING (ID tokens only - access tokens are opaque)
- Microsoft Entra ID: ⚠️ SPECULATIVE/UNTESTED (should work, based on OIDC standards)

Note: Providers can use OIDC discovery to auto-configure issuer and JWKS URI.
Set 'discovery_url' in provider config to enable auto-discovery.
"""

import logging
from typing import Dict, Any, Optional

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
    
    ✅ TESTED AND WORKING with Google ID tokens.
    
    Note: Only ID tokens work. Google access tokens are opaque (not JWTs) and cannot be validated.
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
        "entra": EntraJWTValidator,
        "azure": EntraJWTValidator,  # Alias for Entra
        "azuread": EntraJWTValidator,  # Another alias
    }

    validator_class = validators.get(provider_name)
    if not validator_class:
        raise ValueError(f"Unknown JWT provider: {provider_name}")

    logger.info(f"Creating {provider_name} JWT validator")
    return validator_class(provider_config)
