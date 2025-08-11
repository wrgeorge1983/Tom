from dataclasses import dataclass
from typing import Optional

from netmiko import ConnectHandler

from tom_core.credentials.credentials import (
    YamlCredentialStore,
    SSHCredentials,
    CredentialStore,
)
from tom_core.exceptions import TomException


@dataclass
class NetmikoAdapter:
    host: str
    port: int
    device_type: str
    credential: Optional[SSHCredentials] = None
    connection: Optional[ConnectHandler] = None

    def connect(self):
        if self.credential is None or not self.credential.initialized:
            raise TomException("SSH Credentials not initialized")

        self.connection = ConnectHandler(
            host=self.host,
            username=self.credential.username,
            password=self.credential.password,
            device_type=self.device_type,
            port=self.port,
        )

    def close(self):
        if self.connection is not None:
            self.connection.disconnect()
            self.connection = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        self.close()
        return False

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
            raise TomException("Connection not initialized")

        return self.connection.send_command(command)


if __name__ == "__main__":
    credential_store = YamlCredentialStore("../../../../adhoc_tests/assets.yml")
    adapter = NetmikoAdapter.new_with_credential(
        "192.168.155.227",
        "cisco_ios",
        "first_test",
        22,
        credential_store=credential_store,
    )
    adapter.credential.initialize(credential_store)
    adapter.connect()
    print(adapter.send_command("show ip int brief"))
