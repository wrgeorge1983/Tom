"""HashiCorp Vault credential store plugin."""

import os
from json import JSONDecodeError
from logging import getLogger
from typing import TYPE_CHECKING, TypedDict

import httpx
from pydantic import model_validator
from pydantic_settings import SettingsConfigDict

from tom_worker.credentials.credentials import SSHCredentials
from tom_worker.exceptions import TomException
from tom_worker.Plugins.base import CredentialPlugin, PluginSettings

if TYPE_CHECKING:
    from tom_worker.config import Settings

logger = getLogger(__name__)


class VaultCreds(TypedDict):
    """Type definition for credential data from Vault."""

    username: str
    password: str


class VaultCredentialSettings(PluginSettings):
    """
    Vault Credential Plugin Settings.

    Config file uses prefixed keys: plugin_vault_url, plugin_vault_token, etc.
    Env vars use: TOM_WORKER_PLUGIN_VAULT_URL, TOM_WORKER_PLUGIN_VAULT_TOKEN, etc.
    Code uses: settings.url, settings.token, etc.

    Authentication modes:
    - Token mode (dev): Set 'token' directly
    - AppRole mode (production): Set 'role_id' and 'secret_id'
    """

    url: str
    token: str = ""
    role_id: str = ""
    secret_id: str = ""
    verify_ssl: bool = True
    credential_path_prefix: str = "credentials"

    @model_validator(mode="after")
    def validate_auth_config(self) -> "VaultCredentialSettings":
        """Ensure either token or AppRole credentials are provided."""
        has_token = bool(self.token)
        has_approle = bool(self.role_id and self.secret_id)

        if not has_token and not has_approle:
            raise ValueError(
                "Vault authentication requires either 'token' (for dev mode) "
                "or both 'role_id' and 'secret_id' (for AppRole authentication)"
            )
        return self

    model_config = SettingsConfigDict(
        env_prefix="TOM_WORKER_",
        env_file=os.getenv("TOM_WORKER_ENV_FILE", "foo.env"),
        yaml_file=os.getenv("TOM_WORKER_CONFIG_FILE", "tom_worker_config.yaml"),
        case_sensitive=False,
        extra="forbid",
        plugin_name="vault",  # type: ignore[typeddict-unknown-key]
    )


class VaultClient:
    """HTTP client for HashiCorp Vault API."""

    def __init__(self, vault_addr: str, token: str, verify_ssl: bool = True):
        self.addr = vault_addr.rstrip("/")
        self.token = token
        self.headers = {"X-Vault-Token": token}
        self.verify_ssl = verify_ssl

    async def authenticate_with_approle(self, role_id: str, secret_id: str) -> str:
        """Authenticate using AppRole and return a token.

        :param role_id: AppRole role ID
        :param secret_id: AppRole secret ID
        :return: Vault client token
        :raises TomException: If authentication fails
        """
        url = f"{self.addr}/v1/auth/approle/login"
        payload = {"role_id": role_id, "secret_id": secret_id}

        try:
            async with httpx.AsyncClient(verify=self.verify_ssl) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
                return data["auth"]["client_token"]
        except httpx.HTTPStatusError as e:
            raise TomException(f"Vault AppRole authentication failed: {e}") from e
        except (KeyError, JSONDecodeError) as e:
            raise TomException(f"Invalid AppRole response from Vault: {e}") from e

    async def health_check(self) -> bool:
        """Check Vault connectivity.

        :return: True if Vault is reachable and healthy
        """
        url = f"{self.addr}/v1/sys/health"

        try:
            async with httpx.AsyncClient(verify=self.verify_ssl) as client:
                response = await client.get(url)
                response.raise_for_status()
                return True
        except (httpx.HTTPStatusError, httpx.ConnectError):
            return False

    async def validate_access(self) -> bool:
        """Validate that the token has access to Vault.

        :return: True if token is valid
        :raises TomException: If token is invalid or validation fails
        """
        url = f"{self.addr}/v1/auth/token/lookup-self"

        try:
            async with httpx.AsyncClient(verify=self.verify_ssl) as client:
                response = await client.get(url, headers=self.headers)
                response.raise_for_status()
                return True
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403:
                raise TomException(f"Invalid Vault token: {e}")
            raise TomException(f"Vault token validation failed: {e}")

    async def read_secret(self, path: str) -> VaultCreds:
        """Read a secret from Vault KV v2.

        :param path: Secret path (without 'secret/data/' prefix)
        :return: Secret data dictionary
        :raises TomException: If secret cannot be read
        """
        url = f"{self.addr}/v1/secret/data/{path}"

        async with httpx.AsyncClient(verify=self.verify_ssl) as client:
            response = await client.get(url, headers=self.headers)

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise TomException(f"Secret not found at path: {path}")
            raise TomException(f"Failed to read secret at {path}: {e}") from e

        try:
            data = response.json()
        except JSONDecodeError:
            raise TomException(f"Invalid JSON response from Vault: {response.text}")

        try:
            return data["data"]["data"]
        except KeyError:
            raise TomException(f"Invalid secret data structure from Vault: {data}")

    @classmethod
    async def from_settings(cls, settings: VaultCredentialSettings) -> "VaultClient":
        """Create VaultClient from settings, handling authentication.

        If role_id and secret_id are provided, uses AppRole authentication.
        Otherwise, uses the provided token directly.

        :param settings: Vault plugin settings
        :return: Authenticated VaultClient instance
        :raises TomException: If authentication fails
        """
        vault_addr = settings.url
        verify_ssl = settings.verify_ssl

        if settings.role_id and settings.secret_id:
            # AppRole authentication
            temp_client = cls(vault_addr, "", verify_ssl)
            token = await temp_client.authenticate_with_approle(
                settings.role_id, settings.secret_id
            )
            return cls(vault_addr, token, verify_ssl)
        elif settings.token:
            # Direct token authentication
            return cls(vault_addr, settings.token, verify_ssl)
        else:
            # This should be caught by settings validation, but just in case
            raise TomException(
                "Vault authentication requires either 'token' (for dev mode) "
                "or both 'role_id' and 'secret_id' (for AppRole authentication)"
            )


class VaultCredentialPlugin(CredentialPlugin):
    """HashiCorp Vault credential store plugin.

    Reads credentials from Vault KV v2 secrets engine. Secrets are expected
    at path: secret/data/{credential_path_prefix}/{credential_id}

    Each secret must contain 'username' and 'password' keys.
    """

    name = "vault"
    dependencies = []  # httpx is a core dependency
    settings_class = VaultCredentialSettings

    def __init__(
        self, plugin_settings: VaultCredentialSettings, main_settings: "Settings"
    ):
        self.settings = plugin_settings
        self.main_settings = main_settings
        self._client: VaultClient | None = None

        logger.debug(f"Vault credential plugin initialized for {plugin_settings.url}")

    async def validate(self) -> None:
        """Validate Vault connectivity and authentication.

        :raises TomException: If validation fails
        """
        # Create and authenticate client
        try:
            self._client = await VaultClient.from_settings(self.settings)
        except TomException as e:
            raise TomException(
                f"Vault credential plugin failed to authenticate: {e}\n"
                f"Check your Vault URL ({self.settings.url}) and credentials."
            ) from e

        # Health check
        if not await self._client.health_check():
            raise TomException(
                f"Cannot connect to Vault at {self.settings.url}\n"
                f"Ensure Vault is running and accessible."
            )

        # Validate token access
        try:
            await self._client.validate_access()
        except TomException as e:
            raise TomException(
                f"Vault token validation failed: {e}\n"
                f"Ensure your token has the necessary permissions."
            ) from e

        auth_mode = "AppRole" if self.settings.role_id else "token"
        logger.info(
            f"Vault credential plugin validated: connected to {self.settings.url} "
            f"using {auth_mode} authentication"
        )

    async def get_ssh_credentials(self, credential_id: str) -> SSHCredentials:
        """Retrieve SSH credentials from Vault.

        :param credential_id: The credential identifier
        :return: SSHCredentials with username and password
        :raises TomException: If credential not found or retrieval fails
        """
        if self._client is None:
            # Client not initialized - this shouldn't happen if validate() was called
            self._client = await VaultClient.from_settings(self.settings)

        secret_path = f"{self.settings.credential_path_prefix}/{credential_id}"

        try:
            cred_data = await self._client.read_secret(secret_path)
        except TomException as e:
            raise TomException(
                f"Failed to retrieve credential '{credential_id}' from Vault: {e}"
            ) from e

        if "username" not in cred_data:
            raise TomException(
                f"Vault secret at '{secret_path}' is missing required 'username' field"
            )

        if "password" not in cred_data:
            raise TomException(
                f"Vault secret at '{secret_path}' is missing required 'password' field"
            )

        return SSHCredentials(
            credential_id=credential_id,
            username=cred_data["username"],
            password=cred_data["password"],
        )
