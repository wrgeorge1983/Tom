import logging
import os
from pathlib import Path
from typing import Literal

from pydantic import computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
import saq


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
    swapi_default_cred_name: str = "default"

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
                raise ValueError("api_keys must be a list of strings in the format 'key:user'")
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
        case_sensitive=False,
    )


# Global settings instance - initialized at import time
settings = Settings()
