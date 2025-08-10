import logging
import os
from pathlib import Path

from pydantic import computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    # Credential store settings
    project_root: str = "../../../../"
    credential_file: str = "assets.yml"

    # Tom Core Server settings
    host: str = "0.0.0.0"
    port: int = 8020
    log_level: str | int = "info"  # Input is str, but we convert to int for actual use

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v) -> int:
        if isinstance(v, int):
            return v
        return logging.getLevelName(v.upper())

    @computed_field
    @property
    def credential_path(self) -> str:
        return str(Path(self.project_root) / self.credential_file)

    model_config = SettingsConfigDict(
        env_prefix="TOM_CORE_",
        env_file=os.getenv("TOM_CORE_ENV_FILE", "foo.env"),
        case_sensitive=False,
    )


# Global settings instance - initialized at import time
settings = Settings()
