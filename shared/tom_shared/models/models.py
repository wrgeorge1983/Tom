from pydantic import BaseModel


class NetmikoSendCommandModel(BaseModel):
    host: str
    port: int
    device_type: str
    credential_id: str
    command: str


class ScrapliSendCommandModel(BaseModel):
    host: str
    port: int
    device_type: str
    credential_id: str
    command: str
