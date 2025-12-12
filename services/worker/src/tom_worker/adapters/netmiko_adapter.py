import asyncio
import re
from dataclasses import dataclass
from typing import Optional, Any

from netmiko import ConnectHandler
from netmiko.exceptions import NetmikoAuthenticationException

from tom_shared.models import NetmikoSendCommandModel
from tom_worker.credentials.credentials import SSHCredentials
from tom_worker.exceptions import TomException, AuthenticationException
from tom_worker.Plugins.base import CredentialPlugin


class NetmikoAdapter:
    def __init__(
        self, host: str, port: int, device_type: str, credential: SSHCredentials
    ):
        self.host = host
        self.port = port
        self.device_type = device_type
        self.credential = credential
        self.connection: Optional[Any] = None

    def _connect(self):
        if self.credential is None:
            raise TomException("SSH Credentials missing!")

        try:
            self.connection = ConnectHandler(
                host=self.host,
                username=self.credential.username,
                password=self.credential.password,
                device_type=self.device_type,
                port=self.port,
            )
        except NetmikoAuthenticationException as e:
            # Wrap authentication exceptions so they won't be retried
            raise AuthenticationException(
                f"Authentication failed for {self.host}:{self.port} - {str(e)}"
            ) from e

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
    async def from_model(
        cls, model: NetmikoSendCommandModel, credential_store: CredentialPlugin
    ) -> "NetmikoAdapter":
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

    def _send_commands(self, commands: list[str]) -> dict:
        if self.connection is None:
            raise TomException("Connection not initialized")
        results = {}
        for command in commands:
            result = self.connection.send_command(command)
            while command in results:
                n = re.match(r"(.*)_(\d+)$", command)
                if n:
                    command = n.group(1) + "_" + str(int(n.group(2)) + 1)
                else:
                    command = command + "_1"

            results[command] = result.strip()

        return results

    async def send_commands(self, commands: list[str]) -> dict:
        return await asyncio.to_thread(self._send_commands, commands=commands)
