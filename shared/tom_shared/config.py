import logging
from pathlib import Path
from typing import Literal, Optional, Any

from pydantic import computed_field, field_validator
from pydantic_settings import (
    BaseSettings,
    YamlConfigSettingsSource,
    PydanticBaseSettingsSource,
)


class LoggingYamlConfigSettingsSource(YamlConfigSettingsSource):
    """YAML config source that logs whether the file was found."""

    def __init__(self, settings_cls: type[BaseSettings]):
        # Get yaml_file from model_config to avoid duplication
        yaml_file = settings_cls.model_config.get("yaml_file")
        super().__init__(settings_cls)

        # Use print for immediate visibility during startup before logging is configured
        if yaml_file and Path(yaml_file).exists():
            print(f"INFO: Loading configuration from YAML file: {yaml_file}")
        elif yaml_file:
            print(
                f"WARNING: YAML config file not found: {yaml_file} (using defaults and env vars)"
            )
        else:
            print("DEBUG: No YAML config file specified")


class SharedSettings(BaseSettings):
    """
    Settings class manages configuration options.

    precedence: ENVVARS > env_file > yaml_file > defaults

    :var project_root: Relative path to the project's root directory.
    :type project_root: str

    :var log_level: Logging level. "info", "debug", etc.
    :type log_level: str
    """

    log_level: str | int = "info"  # Input is str, but we convert to int for actual use

    # File settings
    project_root: str = "../../../../"

    # Redis settings
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_username: Optional[str] = None
    redis_password: Optional[str] = (
        None  # if provided without username, use legacy auth
    )
    redis_use_tls: bool = False
    redis_tls_check_hostname: bool = False
    redis_tls_cert_reqs: Literal["none", "optional", "required"] = "none"
    redis_tls_ca_certs: Optional[str] = None
    redis_tls_certfile: Optional[str] = None
    redis_tls_keyfile: Optional[str] = None

    @computed_field
    @property
    def redis_url(self) -> str:
        scheme = "rediss" if self.redis_use_tls else "redis"

        if self.redis_password:
            # legacy auth is just password by itself
            # you DO include the ':' when doing this, technically you're using the 'default user' with an empty username
            auth_string = f":{self.redis_password}@"
            if self.redis_username:
                auth_string = f"{self.redis_username}{auth_string}"

        else:
            auth_string = ""

        url = f"{scheme}://{auth_string}{self.redis_host}:{self.redis_port}/{self.redis_db}"
        if self.redis_use_tls:
            url += f"?ssl_check_hostname={str(self.redis_tls_check_hostname).lower()}"
            url += f"&ssl_cert_reqs={self.redis_tls_cert_reqs}"
            if self.redis_tls_ca_certs:
                url += f"&ssl_ca_certs={self.redis_tls_ca_certs}"
            if self.redis_tls_certfile:
                url += f"&ssl_certfile={self.redis_tls_certfile}"
            if self.redis_tls_keyfile:
                url += f"&ssl_keyfile={self.redis_tls_keyfile}"

        return url

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v) -> int:
        if isinstance(v, int):
            return v
        return logging.getLevelName(v.upper())

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            env_settings,
            dotenv_settings,
            LoggingYamlConfigSettingsSource(settings_cls),
        )
