import asyncio
from dataclasses import dataclass
from typing import Optional

from netmiko import ConnectHandler

from tom_shared.models import NetmikoSendCommandModel
from tom_worker.credentials.credentials import (
    SSHCredentials,
    CredentialStore,
)
from tom_worker.exceptions import TomException


class NetmikoAdapter:
    def __init__(
        self, host: str, port: int, device_type: str, credential: SSHCredentials
    ):
        self.host = host
        self.port = port
        self.device_type = device_type
        self.credential = credential
        self.connection: Optional[ConnectHandler] = None

    def _connect(self):
        if self.credential is None:
            raise TomException("SSH Credentials missing!")

        self.connection = ConnectHandler(
            host=self.host,
            username=self.credential.username,
            password=self.credential.password,
            device_type=self.device_type,
            port=self.port,
        )

    async def connect(self):
        return await asyncio.to_thread(self._connect)

    def _close(self):
        if self.connection is not None:
            self.connection.disconnect()
            self.connection = None

    async def close(self):
        return await asyncio.to_thread(self._close)

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool:
        await self.close()
        return False

    @classmethod
    def from_model(
        cls, model: NetmikoSendCommandModel, credential_store: CredentialStore
    ) -> "NetmikoAdapter":
        credential = credential_store.get_ssh_credentials(model.credential_id)
        return cls(
            host=model.host,
            device_type=model.device_type,
            credential=credential,
            port=model.port,
        )

    def _send_command(self, command: str) -> str:
        if self.connection is None:
            raise TomException("Connection not initialized")

        return self.connection.send_command(command)

    async def send_command(self, command: str) -> str:
        return await asyncio.to_thread(self._send_command, command=command)
