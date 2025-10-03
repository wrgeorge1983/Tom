import logging
import os
from pathlib import Path
from typing import Literal, Optional, Any

from pydantic import BaseModel, computed_field, field_validator
from pydantic_settings import (
    SettingsConfigDict,
)

from tom_shared.config import SharedSettings


class JWTProviderConfig(BaseModel):
    """Configuration for a JWT authentication provider.
    
    OIDC Discovery Support:
    If 'discovery_url' is provided, the provider will use OIDC discovery to
    automatically configure issuer, jwks_uri, and endpoints. This is the
    recommended approach for OIDC-compliant providers.
    
    Minimal config with discovery:
        name: google
        enabled: true
        client_id: "your-client-id"
        discovery_url: "https://accounts.google.com/.well-known/openid-configuration"
    
    Manual config (for providers without OIDC discovery):
        name: duo
        enabled: true
        issuer: "https://sso-xxx.sso.duosecurity.com/oidc/CLIENT_ID"
        client_id: "CLIENT_ID"
        jwks_uri: "https://sso-xxx.sso.duosecurity.com/oidc/CLIENT_ID/jwks"
    """

    name: Literal["duo", "google", "entra"] = "duo"
    enabled: bool = True
    
    # OIDC Discovery (recommended for standard OIDC providers)
    discovery_url: Optional[str] = None  # e.g., "https://accounts.google.com/.well-known/openid-configuration"
    
    # Manual configuration (required if discovery_url not provided)
    issuer: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None  # OAuth client secret for token exchange (rarely needed with PKCE)
    jwks_uri: Optional[str] = None
    audience: Optional[str] = None  # Defaults to client_id if not specified
    leeway_seconds: int = 30

    # OAuth endpoints (auto-discovered if discovery_url provided)
    authorization_url: Optional[str] = None  # OAuth authorization endpoint
    token_url: Optional[str] = None  # OAuth token endpoint
    user_info_url: Optional[str] = None  # OAuth user info endpoint

    # OAuth scopes to request
    scopes: list[str] = ["openid", "email", "profile"]  # Default OIDC scopes

    # Provider-specific fields
    tenant_id: Optional[str] = None  # Microsoft Entra tenant ID (can be used to build discovery_url)


class SolarWindsMatchCriteria(BaseModel):
    """Match criteria for SolarWinds devices."""

    vendor: Optional[str] = None
    description: Optional[str] = None
    caption: Optional[str] = None


class SolarWindsDeviceAction(BaseModel):
    """Action to take when a device matches criteria."""

    adapter: str
    adapter_driver: str
    credential_id: Optional[str] = None
    port: int = 22


class SolarWindsMapping(BaseModel):
    """A single match/action rule for SolarWinds devices."""

    match: SolarWindsMatchCriteria
    action: SolarWindsDeviceAction


class Settings(SharedSettings):
    """
    Settings class manages configuration options.

    precedence: ENVVARS > env_file > defaults
    ENVVARS are prefixed with "TOM_CONTROLLER_" (but are not case sensitive)

    :var project_root: Relative path to the project's root directory.
    :type project_root: str
    :var credential_file: YamlCredentialStore source file (relative to project_root)
    :type credential_file: str

    :var host: Host IP address for the server to bind to.
    :type host: str
    :var port: Port number for the server to bind to.
    :type port: int

    :var log_level: Logging level. "info", "debug", etc.
    :type log_level: str
    """

    # inherits log, project_root, and redis settings from SharedSettings

    # Store settings
    inventory_type: Literal["yaml", "swis"] = "yaml"
    inventory_file: str = "defaultInventory.yml"

    # SolarWinds API settings
    swapi_host: str = ""
    swapi_username: str = ""
    swapi_password: str = ""
    swapi_port: int = 17774
    swapi_device_mappings: list[SolarWindsMapping] = [
        SolarWindsMapping(
            match=SolarWindsMatchCriteria(vendor=".*"),
            action=SolarWindsDeviceAction(
                adapter="netmiko",
                adapter_driver="cisco_ios",
                credential_id="default",
            ),
        )
    ]

    # Tom Core Server settings
    host: str = "0.0.0.0"
    port: int = 8020

    # API Settings
    allow_inline_credentials: bool = False
    auth_mode: Literal["none", "api_key", "jwt", "hybrid"] = "none"
    api_key_headers: list[str] = ["X-API-Key"]
    api_keys: list[str] = []  # "key:user", "key:user"

    # JWT Settings
    jwt_providers: list[JWTProviderConfig] = []
    jwt_require_https: bool = True

    @field_validator("api_keys")
    @classmethod
    def validate_api_keys(cls, v) -> list[str]:
        if not isinstance(v, list):
            raise ValueError("api_keys must be a list of strings")
        for key in v:
            if not isinstance(key, str):
                raise ValueError("api_keys must be a list of strings")
            if ":" not in key:
                raise ValueError(
                    "api_keys must be a list of strings in the format 'key:user'"
                )
        return v

    @computed_field
    @property
    def api_key_users(self) -> dict[str, str]:
        return {
            key: user
            for key_str in self.api_keys
            for key, user in [key_str.split(":", 1)]
        }

    @computed_field
    @property
    def inventory_path(self) -> str:
        return str(Path(self.project_root) / self.inventory_file)

    model_config = SettingsConfigDict(
        env_prefix="TOM_",
        env_file=os.getenv("TOM_ENV_FILE", "foo.env"),
        yaml_file=os.getenv("TOM_CONFIG_FILE", "tom_config.yaml"),
        case_sensitive=False,
    )


# Global settings instance - initialized at import time
settings = Settings()
