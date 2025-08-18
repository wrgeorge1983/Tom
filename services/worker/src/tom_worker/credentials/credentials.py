from dataclasses import dataclass
from typing import Optional

import yaml

from tom_worker.exceptions import TomException


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

    def get_ssh_credentials(self, credential_id: str) -> "SSHCredentials":
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
        cred_data = self.data[credential_id]
        return SSHCredentials(
            credential_id=credential_id,
            username=cred_data["username"],
            password=cred_data["password"],
        )

        # return self.data[credential_id]["username"], self.data[credential_id][
        #     "password"
        # ]


@dataclass
class SSHCredentials:
    credential_id: str
    username: Optional[str] = None
    password: Optional[str] = None
