from dataclasses import dataclass
from typing import Optional

import yaml

from tom_core.exceptions import TomException


class CredentialStore:
    def get_ssh_credentials(self, credential_id: str) -> (str, str):
        raise TomException("Not implemented")


@dataclass
class YamlCredentialStore(CredentialStore):
    filename: str = ""
    data: Optional[dict] = None

    def __init__(self, filename: str):
        self.filename = filename
        with open(filename, "r") as f:
            self.data = yaml.safe_load(f)

    def get_ssh_credentials(self, credential_id: str) -> (str, str):
        if credential_id not in self.data:
            raise TomException(
                f"Credential {credential_id} not found in {self.filename}"
            )

        if (
            "username" not in self.data[credential_id]
            or "password" not in self.data[credential_id]
        ):
            raise TomException(
                f"Credential {credential_id} does missing username or password"
            )

        return self.data[credential_id]["username"], self.data[credential_id][
            "password"
        ]


@dataclass
class SSHCredentials:
    credential_id: str
    username: Optional[str] = None
    password: Optional[str] = None
    initialized: bool = False

    def initialize(self, credential_store: CredentialStore):
        self.username, self.password = credential_store.get_ssh_credentials(
            self.credential_id
        )
        self.initialized = True
