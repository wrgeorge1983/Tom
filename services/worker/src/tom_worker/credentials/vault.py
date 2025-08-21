from json import JSONDecodeError
from typing import TypedDict

import httpx

from tom_worker.exceptions import TomAuthException
from tom_worker.config import Settings
from tom_worker.credentials.credentials import CredentialStore, SSHCredentials


class VaultCreds(TypedDict):
    username: str
    password: str


class VaultClient:
    def __init__(self, vault_addr: str, token: str):
        self.addr = vault_addr.rstrip("/")
        self.token = token
        self.headers = {"X-Vault-Token": token}

    async def health_check(self) -> bool:
        """Validate Vault connectivity and authentication."""
        url = f"{self.addr}/v1/sys/health"

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url)
                response.raise_for_status()
                return True
        except (httpx.HTTPStatusError, httpx.ConnectError):
            return False

    async def validate_access(self) -> bool:
        """Validate that the token has access to read secrets."""
        # Try to read the token's own info to validate auth
        url = f"{self.addr}/v1/auth/token/lookup-self"

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=self.headers)
                response.raise_for_status()
                return True
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403:
                raise TomAuthException(f"Invalid Vault token: {e}")
            raise TomAuthException(f"Vault token validation failed: {e}")

    async def read_secret(self, path: str) -> VaultCreds:
        url = f"{self.addr}/v1/secret/data/{path}"

        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=self.headers)

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise TomAuthException(f"Failed to read secret at {path}: {e}") from e

        try:
            response = response.json()
            return response["data"]["data"]
        except JSONDecodeError:
            raise TomAuthException(f"Invalid JSON response from Vault: {response.text}")
        except KeyError:
            raise TomAuthException(f"Invalid data from Vault: {response}")

    @classmethod
    def from_settings(cls, settings: Settings):
        return cls(settings.vault_url, settings.vault_token)


class VaultCredentialStore(CredentialStore):
    def __init__(self, vault_client: VaultClient):
        self.client = vault_client

    @classmethod
    async def create_and_validate(
        cls, vault_client: VaultClient
    ) -> "VaultCredentialStore":
        """Create a VaultCredentialStore and validate Vault access."""
        # Check basic connectivity
        if not await vault_client.health_check():
            raise TomAuthException(
                "Vault health check failed - cannot connect to Vault"
            )

        # Validate token access
        await vault_client.validate_access()

        return cls(vault_client)

    async def get_ssh_credentials(self, credential_id: str) -> SSHCredentials:
        cred_data = await self.client.read_secret(f"credentials/{credential_id}")
        return SSHCredentials(
            credential_id=credential_id,
            username=cred_data["username"],
            password=cred_data["password"],
        )
