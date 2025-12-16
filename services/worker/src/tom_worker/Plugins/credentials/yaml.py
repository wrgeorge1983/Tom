"""YAML file-based credential store plugin."""

import os
from logging import getLogger
from pathlib import Path
from typing import TYPE_CHECKING

import yaml
from pydantic_settings import SettingsConfigDict

from tom_worker.credentials.credentials import SSHCredentials
from tom_worker.exceptions import TomException
from tom_worker.Plugins.base import CredentialPlugin, PluginSettings

if TYPE_CHECKING:
    from tom_worker.config import Settings

logger = getLogger(__name__)


class YamlCredentialSettings(PluginSettings):
    """
    YAML Credential Plugin Settings.

    Config file uses prefixed keys: plugin_yaml_credential_file
    Env vars use: TOM_WORKER_PLUGIN_YAML_CREDENTIAL_FILE
    Code uses: settings.credential_file
    """

    credential_file: str = "inventory/creds.yml"

    model_config = SettingsConfigDict(
        env_prefix="TOM_WORKER_",
        env_file=os.getenv("TOM_WORKER_ENV_FILE", "foo.env"),
        yaml_file=os.getenv("TOM_WORKER_CONFIG_FILE", "tom_worker_config.yaml"),
        case_sensitive=False,
        extra="forbid",
        plugin_name="yaml",  # type: ignore[typeddict-unknown-key]
    )


class YamlCredentialPlugin(CredentialPlugin):
    """YAML file-based credential store plugin.

    Reads credentials from a YAML file with the following format:

    ```yaml
    credential_id:
      username: myuser
      password: mypassword

    another_credential:
      username: otheruser
      password: otherpassword
    ```
    """

    name = "yaml"
    dependencies = ["yaml"]  # pyyaml is the package name, but 'yaml' is the import name
    settings_class = YamlCredentialSettings

    def __init__(
        self, plugin_settings: YamlCredentialSettings, main_settings: "Settings"
    ):
        self.settings = plugin_settings
        self.main_settings = main_settings
        self._data: dict | None = None

        # Resolve credential file path relative to project root
        self.credential_path = str(
            Path(main_settings.project_root) / plugin_settings.credential_file
        )
        logger.debug(
            f"YAML credential plugin initialized with path: {self.credential_path}"
        )

    def _load_credentials(self) -> dict:
        """Load credentials from YAML file.

        :return: Dictionary of credentials
        :raises TomException: If file cannot be read or parsed
        """
        try:
            with open(self.credential_path, "r") as f:
                data = yaml.safe_load(f)
                if data is None:
                    return {}
                if not isinstance(data, dict):
                    raise TomException(
                        f"Credential file '{self.credential_path}' must contain a YAML dictionary, "
                        f"got {type(data).__name__}"
                    )
                return data
        except FileNotFoundError:
            raise TomException(f"Credential file not found: {self.credential_path}")
        except yaml.YAMLError as e:
            raise TomException(
                f"Invalid YAML in credential file '{self.credential_path}': {e}"
            )

    async def validate(self) -> None:
        """Validate that the credential file exists and is valid YAML.

        :raises TomException: If validation fails
        """
        path = Path(self.credential_path)

        if not path.exists():
            raise TomException(
                f"Credential file not found: {self.credential_path}\n"
                f"Please create this file or update 'plugin_yaml_credential_file' in your config."
            )

        if not path.is_file():
            raise TomException(f"Credential path is not a file: {self.credential_path}")

        # Try to load and parse the file
        self._data = self._load_credentials()

        credential_count = len(self._data)
        logger.info(
            f"YAML credential plugin validated: {credential_count} credential(s) loaded "
            f"from {self.credential_path}"
        )

    async def get_ssh_credentials(self, credential_id: str) -> SSHCredentials:
        """Retrieve SSH credentials by ID.

        :param credential_id: The credential identifier
        :return: SSHCredentials with username and password
        :raises TomException: If credential not found or invalid
        """
        # Lazy load if not already loaded
        if self._data is None:
            self._data = self._load_credentials()

        if credential_id not in self._data:
            available = list(self._data.keys())
            raise TomException(
                f"Credential '{credential_id}' not found in {self.credential_path}. "
                f"Available credentials: {available}"
            )

        cred_entry = self._data[credential_id]

        if not isinstance(cred_entry, dict):
            raise TomException(
                f"Credential '{credential_id}' must be a dictionary with 'username' and 'password' keys, "
                f"got {type(cred_entry).__name__}"
            )

        if "username" not in cred_entry:
            raise TomException(
                f"Credential '{credential_id}' is missing required 'username' field"
            )

        if "password" not in cred_entry:
            raise TomException(
                f"Credential '{credential_id}' is missing required 'password' field"
            )

        return SSHCredentials(
            credential_id=credential_id,
            username=cred_entry["username"],
            password=cred_entry["password"],
        )
