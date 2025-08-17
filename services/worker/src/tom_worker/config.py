import logging
import os
from pathlib import Path

from pydantic import computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Settings class manages configuration options.

    precedence: ENVVARS > env_file > defaults
    ENVVARS are prefixed with "TOM_WORKER_" (but are not case sensitive)

    :var project_root: Relative path to the project's root directory.
    :type project_root: str

    :var log_level: Logging level. "info", "debug", etc.
    :type log_level: str
    """

    # File settings
    project_root: str = "../../../../"
    credential_file: str = "defaultCreds.yml"

    # Tom Core Server settings
    log_level: str | int = "info"  # Input is str, but we convert to int for actual use

    # Redis settings
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    # TODO: SSL, Auth, Etc.

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
        env_prefix="TOM_WORKER_",
        env_file=os.getenv("TOM_WORKER_ENV_FILE", "foo.env"),
        case_sensitive=False,
    )


# Global settings instance - initialized at import time
settings = Settings()
