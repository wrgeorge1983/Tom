import logging
import os
from pathlib import Path
from typing import Literal

from pydantic import computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from tom_shared.config import SharedSettings


class Settings(SharedSettings):
    """
    Settings class manages configuration options.

    precedence: ENVVARS > env_file > defaults
    ENVVARS are prefixed with "TOM_WORKER_" (but are not case sensitive)

    :var project_root: Relative path to the project's root directory.
    :type project_root: str

    :var log_level: Logging level. "info", "debug", etc.
    :type log_level: str
    """

    # inherits log, project_root, and redis settings from SharedSettings

    # credential stores

    # - YAML store
    credential_file: str = "defaultCreds.yml"

    # - Vault store
    vault_url: str = ""  # e.g. http://localhost:8200"
    vault_token: str = (
        ""  # e.g. s.csdfssdfs3823j   (or 'myroot' if you are IN DEV ONLY)
    )
    vault_role_id: str = ""  # AppRole role_id for production deployments
    vault_secret_id: str = ""  # AppRole secret_id for production deployments
    vault_verify_ssl: bool = False  # Set to True to enable SSL verification

    credential_store: Literal["yaml", "vault"] = "yaml"

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
