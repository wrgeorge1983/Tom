import os
from dataclasses import dataclass
from typing import Optional

import yaml


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
            # First try to open the file directly
            try:
                with open(self.filename, "r") as f:
                    self.data = yaml.safe_load(f)
            except FileNotFoundError:
                # If not found, try to open from project root
                project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                full_path = os.path.join(project_root, self.filename)
                with open(full_path, "r") as f:
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
