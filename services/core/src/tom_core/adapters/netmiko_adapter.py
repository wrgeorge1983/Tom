from dataclasses import dataclass
from typing import Optional

from netmiko import ConnectHandler

from tom_core.credentials.credentials import YamlCredentialStore, SSHCredentials


@dataclass
class NetmikoAdapter:
    host: str
    device_type: str
    port: int
    credential: Optional[SSHCredentials] = None
    connection: Optional[ConnectHandler] = None

    def connect(self):
        if self.credential is None or not self.credential.initialized:
            raise Exception("SSH Credentials not initialized")


        self.connection = ConnectHandler(
            host=self.host,
            username=self.credential.username,
            password=self.credential.password,
            device_type=self.device_type,
            port=self.port,
        )

    @classmethod
    def new_with_credential(cls, host: str, device_type: str, credential_id: str, port: int = 22):
        return cls(host=host, device_type=device_type, credential=SSHCredentials(credential_id), port=port)

    def send_command(self, command: str) -> str:
        if self.connection is None:
            raise Exception("Connection not initialized")

        return self.connection.send_command(command)

if __name__ == "__main__":

    credential_store = YamlCredentialStore("../../../../adhoc_tests/assets.yml")
    adapter = NetmikoAdapter.new_with_credential("192.168.155.227", "cisco_ios", "first_test", 22, )
    adapter.credential.initialize(credential_store)
    adapter.connect()
    print(adapter.send_command("show ip int brief"))
