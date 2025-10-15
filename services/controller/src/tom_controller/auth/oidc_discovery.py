"""OIDC Discovery helper for automatic provider configuration."""

import logging
from typing import Dict, Any, Optional
from urllib.parse import urljoin

import httpx


logger = logging.getLogger(__name__)


class OIDCDiscovery:
    """Handle OIDC provider discovery via .well-known endpoint."""

    def __init__(self, issuer_or_discovery_url: str):
        """Initialize with either issuer URL or discovery URL.
        
        Args:
            issuer_or_discovery_url: Either the issuer URL or the full discovery URL
        """
        if "/.well-known/openid-configuration" in issuer_or_discovery_url:
            self.discovery_url = issuer_or_discovery_url
        else:
            # Build discovery URL from issuer
            issuer = issuer_or_discovery_url.rstrip('/')
            self.discovery_url = f"{issuer}/.well-known/openid-configuration"
        
        self._discovery_cache: Optional[Dict[str, Any]] = None
        self._http_client: Optional[httpx.AsyncClient] = None

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=10.0)
        return self._http_client

    async def close(self):
        """Clean up resources."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    async def discover(self) -> Dict[str, Any]:
        """Fetch and return OIDC discovery document.
        
        Returns:
            Dictionary containing OIDC provider metadata
            
        Raises:
            httpx.HTTPError: If discovery fails
        """
        if self._discovery_cache:
            logger.debug(f"Using cached discovery for {self.discovery_url}")
            return self._discovery_cache

        logger.info(f"Fetching OIDC discovery from {self.discovery_url}")
        
        try:
            client = await self._get_http_client()
            response = await client.get(self.discovery_url)
            response.raise_for_status()
            
            discovery_doc = response.json()
            self._discovery_cache = discovery_doc
            
            logger.info(f"Discovery successful: issuer={discovery_doc.get('issuer')}")
            return discovery_doc
            
        except httpx.HTTPError as e:
            logger.error(f"OIDC discovery failed for {self.discovery_url}: {e}")
            raise

    async def get_jwks_uri(self) -> str:
        """Get JWKS URI from discovery."""
        doc = await self.discover()
        return doc["jwks_uri"]

    async def get_issuer(self) -> str:
        """Get issuer from discovery."""
        doc = await self.discover()
        return doc["issuer"]

    async def get_authorization_endpoint(self) -> str:
        """Get authorization endpoint from discovery."""
        doc = await self.discover()
        return doc["authorization_endpoint"]

    async def get_token_endpoint(self) -> str:
        """Get token endpoint from discovery."""
        doc = await self.discover()
        return doc["token_endpoint"]

    async def get_userinfo_endpoint(self) -> Optional[str]:
        """Get userinfo endpoint from discovery."""
        doc = await self.discover()
        return doc.get("userinfo_endpoint")

    async def supports_pkce(self) -> bool:
        """Check if provider supports PKCE."""
        doc = await self.discover()
        methods = doc.get("code_challenge_methods_supported", [])
        return "S256" in methods

    async def get_supported_scopes(self) -> list[str]:
        """Get list of supported scopes."""
        doc = await self.discover()
        return doc.get("scopes_supported", [])


async def discover_provider(issuer_or_discovery_url: str) -> Dict[str, Any]:
    """Convenience function to discover provider configuration.
    
    Args:
        issuer_or_discovery_url: Issuer URL or full discovery URL
        
    Returns:
        Dictionary with provider configuration
    """
    discovery = OIDCDiscovery(issuer_or_discovery_url)
    try:
        doc = await discovery.discover()
        return {
            "issuer": doc["issuer"],
            "jwks_uri": doc["jwks_uri"],
            "authorization_endpoint": doc.get("authorization_endpoint"),
            "token_endpoint": doc.get("token_endpoint"),
            "userinfo_endpoint": doc.get("userinfo_endpoint"),
            "scopes_supported": doc.get("scopes_supported", []),
            "supports_pkce": "S256" in doc.get("code_challenge_methods_supported", []),
        }
    finally:
        await discovery.close()


# Common provider discovery URLs for convenience
KNOWN_PROVIDERS = {
    "google": "https://accounts.google.com/.well-known/openid-configuration",
    "microsoft": "https://login.microsoftonline.com/common/v2.0/.well-known/openid-configuration",
    "okta": "https://{domain}.okta.com/.well-known/openid-configuration",
    "auth0": "https://{domain}.auth0.com/.well-known/openid-configuration",
}


def get_discovery_url(provider: str, domain: Optional[str] = None, tenant: Optional[str] = None) -> Optional[str]:
    """Get discovery URL for a known provider.
    
    Args:
        provider: Provider name (google, microsoft, okta, auth0)
        domain: Domain for providers like Okta/Auth0
        tenant: Tenant ID for Microsoft (defaults to 'common')
        
    Returns:
        Discovery URL or None if provider unknown
    """
    if provider == "google":
        return KNOWN_PROVIDERS["google"]
    elif provider == "microsoft":
        tenant = tenant or "common"
        return f"https://login.microsoftonline.com/{tenant}/v2.0/.well-known/openid-configuration"
    elif provider == "okta" and domain:
        return f"https://{domain}.okta.com/.well-known/openid-configuration"
    elif provider == "auth0" and domain:
        return f"https://{domain}.auth0.com/.well-known/openid-configuration"
    
    return None
