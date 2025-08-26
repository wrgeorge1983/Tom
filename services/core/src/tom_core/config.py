import logging
import os
from pathlib import Path
from typing import Literal, Optional, Any

from pydantic import BaseModel, computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict, YamlConfigSettingsSource, PydanticBaseSettingsSource
import saq


class LoggingYamlConfigSettingsSource(YamlConfigSettingsSource):
    """YAML config source that logs whether the file was found."""
    
    def __init__(self, settings_cls: type[BaseSettings]):
        # Get yaml_file from model_config to avoid duplication
        yaml_file = getattr(settings_cls.model_config, 'yaml_file', None)
        super().__init__(settings_cls, yaml_file)
        
        # Use print for immediate visibility during startup before logging is configured
        if yaml_file and Path(yaml_file).exists():
            print(f"INFO: Loading configuration from YAML file: {yaml_file}")
        elif yaml_file:
            print(f"WARNING: YAML config file not found: {yaml_file} (using defaults and env vars)")
        else:
            print("DEBUG: No YAML config file specified")


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


class Settings(BaseSettings):
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

    # File settings
    project_root: str = "../../../../"

    # Store settings
    inventory_type: Literal["yaml", "swis"] = "yaml"
    inventory_file: str = "defaultInventory.yml"

    # Redis settings
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    # TODO: SSL, Auth, Etc.

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
            )
        )
    ]

    # Tom Core Server settings
    host: str = "0.0.0.0"
    port: int = 8020
    log_level: str | int = "info"  # Input is str, but we convert to int for actual use

    # API Settings
    allow_inline_credentials: bool = False
    auth_mode: Literal["none", "api_key", "oauth2"] = "none"
    api_key_headers: list[str] = ["X-API-Key"]
    api_keys: list[str] = []  # "key:user", "key:user"

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v) -> int:
        if isinstance(v, int):
            return v
        return logging.getLevelName(v.upper())

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
    def credential_path(self) -> str:
        return str(Path(self.project_root) / self.credential_file)

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

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return env_settings, dotenv_settings, LoggingYamlConfigSettingsSource(settings_cls),


# Global settings instance - initialized at import time
settings = Settings()
