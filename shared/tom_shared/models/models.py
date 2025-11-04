from typing import Literal, Union, Optional

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
    commands: list[str]
    credential: CredentialSource = Field(discriminator="type")
    use_cache: bool = True
    cache_refresh: bool = False
    cache_ttl: Optional[int] = None


class ScrapliSendCommandModel(BaseModel):
    host: str
    port: int
    device_type: str
    commands: list[str]
    credential: CredentialSource = Field(discriminator="type")
    use_cache: bool = True
    cache_refresh: bool = False
    cache_ttl: Optional[int] = None
