from typing import Literal

from fastapi import APIRouter, Depends, Request

from tom_core.adapters.netmiko_adapter import NetmikoAdapter
from tom_core.adapters.scrapli_adapter import ScrapliAsyncAdapter
from tom_core.credentials.credentials import CredentialStore
from tom_core.exceptions import TomException
from tom_core.inventory.inventory import (
    InventoryStore,
    DeviceConfig,
)

router = APIRouter()


def get_credential_store(request: Request) -> CredentialStore:
    return request.app.state.credential_store


def get_inventory_store(request: Request) -> InventoryStore:
    return request.app.state.inventory_store


@router.get("/")
async def root():
    return {"message": "Hello World"}


@router.get("/raw/send_netmiko_command")
async def send_netmiko_command(
    host: str,
    device_type: str,
    command: str,
    credential_id: str,
    port: int = 22,
    credential_store: CredentialStore = Depends(get_credential_store),
):
    adapter = NetmikoAdapter.new_with_credential(
        host=host,
        device_type=device_type,
        credential_id=credential_id,
        port=port,
        credential_store=credential_store,
    )
    with adapter:
        result = adapter.send_command(command)
    return {"message": result}


@router.get("/raw/send_scrapli_command")
async def send_scrapli_command(
    host: str,
    device_type: str,
    command: str,
    credential_id: str,
    port: int = 22,
    credential_store: CredentialStore = Depends(get_credential_store),
):
    adapter = ScrapliAsyncAdapter.new_with_credential(
        host=host,
        device_type=device_type,
        credential_id=credential_id,
        port=port,
        credential_store=credential_store,
    )
    async with adapter:
        result = await adapter.send_command(command)

    return {"message": result}


@router.get("/inventory/{device_name}")
async def inventory(
    device_name: str, inventory_store: InventoryStore = Depends(get_inventory_store)
) -> DeviceConfig:
    return inventory_store.get_device_config(device_name)


@router.get("/device/{device_name}/send_command")
async def send_inventory_command(
    device_name: str,
    command: str,
    inventory_store: InventoryStore = Depends(get_inventory_store),
    credential_store: CredentialStore = Depends(get_credential_store),
) -> dict[Literal["message"], str]:
    device_config = inventory_store.get_device_config(device_name)
    credential = credential_store.get_ssh_credentials(device_config.credential_id)

    if device_config.adapter == "netmiko":
        adapter = NetmikoAdapter.new_with_credential(
            host=device_config.host,
            device_type=device_config.adapter_driver,
            credential_id=device_config.credential_id,
            port=device_config.port,
            credential_store=credential_store,
        )
        with adapter:
            result = adapter.send_command(command)

    elif device_config.adapter == "scrapli":
        adapter = ScrapliAsyncAdapter.new_with_credential(
            host=device_config.host,
            device_type=device_config.adapter_driver,
            credential_id=device_config.credential_id,
            port=device_config.port,
            credential_store=credential_store,
        )
        async with adapter:
            result = await adapter.send_command(command)

    else:
        raise TomException(f"Unknown device type {type(device_config)}")

    return {"message": result}
