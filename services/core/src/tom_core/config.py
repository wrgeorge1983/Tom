import os
from pathlib import Path

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Tom Core service settings."""

    # Credential store settings
    project_root: str = "../../../../"
    credential_file: str = "assets.yml"

    # Tom Core Server settings
    host: str = "0.0.0.0"
    port: int = 8020
    log_level: str = "info"

    model_config = SettingsConfigDict(
        env_prefix = "TOM_CORE_",
        env_file = os.getenv("TOM_CORE_ENV_FILE", 'foo.env'),
        case_sensitive=False,
    )

    @computed_field
    @property
    def credential_path(self) -> str:
        return str(Path(self.project_root) / self.credential_file)

# Global settings instance - initialized at import time
settings = Settings()
