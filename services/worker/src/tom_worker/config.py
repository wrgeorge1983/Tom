import logging
import os

from pydantic_settings import BaseSettings, SettingsConfigDict

from tom_shared.config import SharedSettings


class Settings(SharedSettings):
    """
    Worker settings class manages configuration options.

    precedence: ENVVARS > env_file > yaml_file > defaults
    ENVVARS are prefixed with "TOM_WORKER_" (but are not case sensitive)

    :var project_root: Relative path to the project's root directory.
    :type project_root: str

    :var log_level: Logging level. "info", "debug", etc.
    :type log_level: str
    """

    # inherits log, project_root, and redis settings from SharedSettings

    # Credential plugin selection (vault recommended for production)
    credential_plugin: str = "vault"

    model_config = SettingsConfigDict(
        env_prefix="TOM_WORKER_",
        env_file=os.getenv("TOM_WORKER_ENV_FILE", "foo.env"),
        yaml_file=os.getenv("TOM_WORKER_CONFIG_FILE", "tom_worker_config.yaml"),
        case_sensitive=False,
    )


# Global settings instance - initialized at import time
settings = Settings()
