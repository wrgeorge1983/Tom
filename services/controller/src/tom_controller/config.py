import logging
import os
from pathlib import Path
from typing import Literal, Optional, Any

from pydantic import BaseModel, ConfigDict, computed_field, field_validator
from pydantic_settings import (
    SettingsConfigDict,
)

from tom_shared.config import SharedSettings


class JWTProviderConfig(BaseModel):
    """Configuration for a JWT authentication provider.
    
    Tom validates JWTs using OIDC discovery. Clients obtain tokens from their
    OAuth provider and present them to Tom for validation.
    
    Required configuration:
        name: google
        enabled: true
        client_id: "your-client-id"
        discovery_url: "https://accounts.google.com/.well-known/openid-configuration"
    """

    name: Literal["duo", "google", "entra"] = "duo"
    enabled: bool = True
    
    # OIDC Discovery (required)
    discovery_url: str
    client_id: str
    
    # Optional JWT validation settings
    # audience can be a string or a list of strings (OIDC allows both)
    audience: Optional[str | list[str]] = None  # Defaults to client_id if not specified
    leeway_seconds: int = 30
    tenant_id: Optional[str] = None  # Microsoft Entra tenant ID

    # OAuth test endpoints (optional - only used if oauth_test_enabled: true)
    oauth_test_client_secret: Optional[str] = None
    oauth_test_scopes: list[str] = ["openid", "email", "profile"]
    
    model_config = ConfigDict(extra="forbid")

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
    # When true (default false), logs may include potentially sensitive user/token details.
    # Keep this false in production for safer logs.
    permit_logging_user_details: bool = False

    # Simple access control for JWT-authenticated users (OAuth)
    # Precedence: allowed_users > allowed_domains > allowed_user_regex
    # Any match grants access; if all lists are empty, allow all authenticated users.
    allowed_users: list[str] = []
    allowed_domains: list[str] = []
    allowed_user_regex: list[str] = []
    
    # OAuth Test Endpoints (optional - for testing only)
    # These endpoints help test OAuth flows without building a client
    # In production, clients should handle OAuth and send JWTs to Tom
    oauth_test_enabled: bool = False

    # Parsing template directories
    textfsm_template_dir: str = "/app/templates/textfsm"
    ttp_template_dir: str = "/app/templates/ttp"

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

    @field_validator("allowed_user_regex")
    @classmethod
    def validate_allowed_user_regex(cls, v) -> list[str]:
        if not isinstance(v, list):
            raise ValueError("allowed_user_regex must be a list of strings")
        
        import re
        for i, pattern in enumerate(v):
            if not isinstance(pattern, str):
                raise ValueError(f"allowed_user_regex[{i}] must be a string")
            try:
                re.compile(pattern)
            except re.error as e:
                raise ValueError(
                    f"allowed_user_regex[{i}] is not a valid regex pattern: '{pattern}' - {e}"
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
        extra="forbid",
    )


# Global settings instance - initialized at import time
settings = Settings()
