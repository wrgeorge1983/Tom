import re
from dataclasses import dataclass, field
from typing import Optional, Type

from scrapli.driver import AsyncNetworkDriver
from scrapli.driver.core import (
    AsyncEOSDriver,
    AsyncIOSXEDriver,
    AsyncNXOSDriver,
    AsyncIOSXRDriver,
    AsyncJunosDriver,
)
from scrapli.exceptions import ScrapliAuthenticationFailed

from tom_shared.models import ScrapliSendCommandModel
from tom_worker.credentials.credentials import SSHCredentials
from tom_worker.exceptions import TomException, AuthenticationException
from tom_worker.Plugins.base import CredentialPlugin


valid_async_drivers = {
    "cisco_iosxe": AsyncIOSXEDriver,
    "cisco_nxos": AsyncNXOSDriver,
    "cisco_iosxr": AsyncIOSXRDriver,
    "arista_eos": AsyncEOSDriver,
    "juniper_junos": AsyncJunosDriver,
}


class ScrapliAsyncAdapter:
    def __init__(
        self, host: str, port: int, device_type: str, credential: SSHCredentials
    ):
        self.host = host
        self.port = port
        self.device_type = device_type
        self.credential = credential
        self.connection: Optional[AsyncNetworkDriver] = None

        self._driver_class = self._resolve_driver(self.device_type)

        # connection is created now, but doesn't touch the network until .open() is called
        self.connection = self._driver_class(
            host=self.host,
            port=self.port,
            auth_username=self.credential.username,
            auth_password=self.credential.password,
            transport="asyncssh",
            auth_strict_key=False,
        )

    @classmethod
    def _resolve_driver(cls, device_type: str) -> Type[AsyncNetworkDriver]:
        result = valid_async_drivers.get(device_type)
        if result is None:
            raise TomException(f"Device type {device_type} not supported")

        return result

    async def connect(self):
        if self.connection is not None:
            try:
                await self.connection.open()
            except ScrapliAuthenticationFailed as e:
                # Wrap authentication exceptions so they won't be retried
                raise AuthenticationException(
                    f"Authentication failed for {self.host}:{self.port} - {str(e)}"
                ) from e

    async def close(self):
        if self.connection.isalive():
            await self.connection.close()
            self.connection = None

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool:
        await self.close()
        return False

    @classmethod
    async def from_model(
        cls, model: ScrapliSendCommandModel, credential_store: CredentialPlugin
    ) -> "ScrapliAsyncAdapter":
        if model.credential.type == "stored":
            credential = await credential_store.get_ssh_credentials(
                model.credential.credential_id
            )
        elif model.credential.type == "inlineSSH":
            credential = SSHCredentials(
                "inline", model.credential.username, model.credential.password
            )
        else:
            raise TomException(f"Credential type {model.credential.type} not supported")

        return cls(
            host=model.host,
            device_type=model.device_type,
            credential=credential,
            port=model.port,
        )

    async def send_commands(self, commands: list[str]) -> dict[str, str]:
        if self.connection is None:
            raise TomException("Connection not initialized")
        results = {}
        for command in commands:
            result = await self.connection.send_command(command)
            while command in results:
                n = re.match(r"(.*)_(\d+)$", command)
                if n:
                    command = n.group(1) + "_" + str(int(n.group(2)) + 1)
                else:
                    command = command + "_1"

            results[command] = result.result

        return results
