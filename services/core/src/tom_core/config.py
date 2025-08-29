import logging
import os
from pathlib import Path
from typing import Literal, Optional, Any

from pydantic import BaseModel, computed_field, field_validator
from pydantic_settings import (
    SettingsConfigDict,
)

from tom_shared.config import SharedSettings


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
    ENVVARS are prefixed with "TOM_CORE_" (but are not case sensitive)

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
    auth_mode: Literal["none", "api_key", "oauth2"] = "none"
    api_key_headers: list[str] = ["X-API-Key"]
    api_keys: list[str] = []  # "key:user", "key:user"

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
        env_prefix="TOM_CORE_",
        env_file=os.getenv("TOM_CORE_ENV_FILE", "foo.env"),
        yaml_file=os.getenv("TOM_CORE_CONFIG_FILE", "tom_core_config.yaml"),
        case_sensitive=False,
    )


# Global settings instance - initialized at import time
settings = Settings()
