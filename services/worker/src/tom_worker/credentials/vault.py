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
    def __init__(self, vault_addr: str, token: str, verify_ssl: bool = True):
        self.addr = vault_addr.rstrip("/")
        self.token = token
        self.headers = {"X-Vault-Token": token}
        self.verify_ssl = verify_ssl
    
    async def authenticate_with_approle(self, role_id: str, secret_id: str) -> str:
        """Authenticate using AppRole and return a token."""
        url = f"{self.addr}/v1/auth/approle/login"
        payload = {
            "role_id": role_id,
            "secret_id": secret_id
        }
        
        try:
            async with httpx.AsyncClient(verify=self.verify_ssl) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
                return data["auth"]["client_token"]
        except httpx.HTTPStatusError as e:
            raise TomAuthException(f"AppRole authentication failed: {e}") from e
        except (KeyError, JSONDecodeError) as e:
            raise TomAuthException(f"Invalid AppRole response from Vault: {e}") from e

    async def health_check(self) -> bool:
        """Validate Vault connectivity and authentication."""
        url = f"{self.addr}/v1/sys/health"

        try:
            async with httpx.AsyncClient(verify=self.verify_ssl) as client:
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
            async with httpx.AsyncClient(verify=self.verify_ssl) as client:
                response = await client.get(url, headers=self.headers)
                response.raise_for_status()
                return True
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403:
                raise TomAuthException(f"Invalid Vault token: {e}")
            raise TomAuthException(f"Vault token validation failed: {e}")

    async def read_secret(self, path: str) -> VaultCreds:
        url = f"{self.addr}/v1/secret/data/{path}"

        async with httpx.AsyncClient(verify=self.verify_ssl) as client:
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
    async def from_settings(cls, settings: Settings):
        """Create VaultClient from settings, auto-detecting authentication mode.
        
        If vault_role_id and vault_secret_id are provided, uses AppRole authentication.
        Otherwise, falls back to direct token authentication (dev mode).
        """
        vault_addr = settings.vault_url
        verify_ssl = settings.vault_verify_ssl
        
        if settings.vault_role_id and settings.vault_secret_id:
            temp_client = cls(vault_addr, "", verify_ssl)
            token = await temp_client.authenticate_with_approle(
                settings.vault_role_id, 
                settings.vault_secret_id
            )
            return cls(vault_addr, token, verify_ssl)
        elif settings.vault_token:
            return cls(vault_addr, settings.vault_token, verify_ssl)
        else:
            raise TomAuthException(
                "Vault authentication requires either (vault_token) for dev mode "
                "or (vault_role_id + vault_secret_id) for AppRole authentication"
            )


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
