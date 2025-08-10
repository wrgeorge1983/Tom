from dataclasses import dataclass
from typing import Optional

import yaml
from netmiko import ConnectHandler

@dataclass
class CredentialStore:
    def get_ssh_credentials(self, credential_id: str) -> (str, str):
        raise Exception("Not implemented")

@dataclass
class YamlCredentialStore(CredentialStore):
    filename: str
    data: Optional[dict] = None
    def __post_init__(self):
        if self.data is None:
            with open(self.filename, "r") as f:
                self.data = yaml.safe_load(f)

    def get_ssh_credentials(self, credential_id: str) -> (str, str):
        if credential_id not in self.data:
            raise Exception(f"Credential {credential_id} not found in {self.filename}")

        if "username" not in self.data[credential_id] or "password" not in self.data[credential_id]:
            raise Exception(f"Credential {credential_id} does missing username or password")

        return self.data[credential_id]["username"], self.data[credential_id]["password"]


@dataclass
class SSHCredentials:
    credential_id: str
    username: Optional[str] = None
    password: Optional[str] = None
    initialized: bool = False

    def initialize(self, credential_store: CredentialStore):
        self.username, self.password = credential_store.get_ssh_credentials(self.credential_id)
        self.initialized = True

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

