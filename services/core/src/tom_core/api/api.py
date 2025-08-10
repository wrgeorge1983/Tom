from urllib.request import Request

from fastapi import APIRouter, Depends, Request

from tom_core.adapters.netmiko_adapter import NetmikoAdapter
from tom_core.credentials.credentials import YamlCredentialStore

router = APIRouter()


def get_credential_store(request: Request):
    return request.app.state.credential_store


@router.get("/")
async def root():
    return {"message": "Hello World"}


@router.get("/send_command")
async def send_netmiko_command(
    host: str,
    device_type: str,
    command: str,
    credential_id: str,
    port: int = 22,
    credential_store: YamlCredentialStore = Depends(get_credential_store),
):
    adapter = NetmikoAdapter.new_with_credential(
        host=host,
        device_type=device_type,
        credential_id=credential_id,
        port=port,
        credential_store=credential_store,
    )
    adapter.connect()
    result = adapter.send_command(command)
    return {"message": result}
