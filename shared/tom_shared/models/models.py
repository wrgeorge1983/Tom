from typing import Literal

from pydantic import BaseModel, Field


class StoredCredential(BaseModel):
    type: Literal["stored"] = "stored"
    credential_id: str

class InlineSSHCredential(BaseModel):
    type: Literal["inlineSSH"] = "inlineSSH"
    username: str
    password: str = Field(None, repr=False)


CredentialSource = StoredCredential | InlineSSHCredential


class NetmikoSendCommandModel(BaseModel):
    host: str
    port: int
    device_type: str
    command: str
    credential: CredentialSource = Field(discriminator="type")


class ScrapliSendCommandModel(BaseModel):
    host: str
    port: int
    device_type: str
    command: str
    credential: CredentialSource = Field(discriminator="type")
