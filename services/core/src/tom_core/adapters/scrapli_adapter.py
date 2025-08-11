from dataclasses import dataclass, field
from typing import Optional, Type

from scrapli.driver import NetworkDriver, AsyncNetworkDriver
from scrapli.driver.base.base_driver import BaseDriver
from scrapli.driver.core import (
    EOSDriver,
    IOSXEDriver,
    NXOSDriver,
    IOSXRDriver,
    JunosDriver,
)
from scrapli.driver.core import (
    AsyncEOSDriver,
    AsyncIOSXEDriver,
    AsyncNXOSDriver,
    AsyncIOSXRDriver,
    AsyncJunosDriver,
)
from tom_core.credentials.credentials import SSHCredentials, CredentialStore

valid_sync_drivers = {
    "cisco_iosxe": IOSXEDriver,
    "cisco_nxos": NXOSDriver,
    "cisco_iosxr": IOSXRDriver,
    "arista_eos": EOSDriver,
    "juniper_junos": JunosDriver,
}

valid_async_drivers = {
    "cisco_iosxe": AsyncIOSXEDriver,
    "cisco_nxos": AsyncNXOSDriver,
    "cisco_iosxr": AsyncIOSXRDriver,
    "arista_eos": AsyncEOSDriver,
    "juniper_junos": AsyncJunosDriver,
}


class SyncDriver:
    pass


@dataclass
class ScrapliSyncAdapter:
    host: str
    port: int
    device_type: str
    credential: Optional[SSHCredentials] = None
    connection: Optional[NetworkDriver] = None
    _driver_class: Optional[Type[NetworkDriver]] = field(default=None, init=False)

    def __post_init__(self):
        self._driver_class = self._resolve_driver(self.device_type)

        if self.credential is None or not self.credential.initialized:
            raise Exception("SSH Credentials not initialized")

        self.connection = self._driver_class(  # scrapli doesn't initiate until calling .open()
            host=self.host,
            port=self.port,
            auth_username=self.credential.username,
            auth_password=self.credential.password,
        )

    @classmethod
    def _resolve_driver(cls, device_type: str) -> Type[NetworkDriver]:
        result = valid_sync_drivers.get(device_type)
        if result is None:
            raise Exception(f"Device type {device_type} not supported")

        return result

    def connect(self):
        if self.connection is None or not self.credential.initialized:
            raise Exception("Connection not initialized")

        self.connection.open()

    @classmethod
    def new_with_credential(
        cls,
        host: str,
        device_type: str,
        credential_id: str,
        port: int,
        credential_store: CredentialStore,
    ):
        credential = SSHCredentials(credential_id)
        credential.initialize(credential_store)
        return cls(host=host, device_type=device_type, credential=credential, port=port)

    def send_command(self, command: str) -> str:
        if self.connection is None:
            raise Exception("Connection not initialized")

        return self.connection.send_command(command).result


@dataclass
class ScrapliAsyncAdapter:
    host: str
    port: int
    device_type: str
    credential: Optional[SSHCredentials] = None
    connection: Optional[AsyncNetworkDriver] = None
    _driver_class: Optional[Type[AsyncNetworkDriver]] = field(default=None, init=False)

    def __post_init__(self):
        self._driver_class = self._resolve_driver(self.device_type)

        if self.credential is None or not self.credential.initialized:
            raise Exception("SSH Credentials not initialized")

        self.connection = self._driver_class(  # scrapli doesn't initiate until calling .open()
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
            raise Exception(f"Device type {device_type} not supported")

        return result

    async def connect(self):
        if self.connection is None or not self.credential.initialized:
            raise Exception("Connection not initialized")
        await self.connection.open()

    @classmethod
    def new_with_credential(
        cls,
        host: str,
        device_type: str,
        credential_id: str,
        port: int,
        credential_store: CredentialStore,
    ):
        credential = SSHCredentials(credential_id)
        credential.initialize(credential_store)
        return cls(host=host, device_type=device_type, credential=credential, port=port)

    async def send_command(self, command: str) -> str:
        if self.connection is None:
            raise Exception("Connection not initialized")
        return (await self.connection.send_command(command)).result
