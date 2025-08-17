from typing import Literal
from urllib import request

from fastapi import APIRouter, Depends, Request
import saq

from shared.models import NetmikoSendCommandModel, ScrapliSendCommandModel
from tom_core.exceptions import TomException
from tom_core.inventory.inventory import (
    InventoryStore,
    DeviceConfig,
)

router = APIRouter()


def get_inventory_store(request: Request) -> InventoryStore:
    return request.app.state.inventory_store


@router.get("/")
async def root():
    return {"message": "Hello World"}


@router.get("/foo")
async def foo(request: Request):
    queue: saq.Queue = request.app.state.queue
    job = await queue.enqueue("foo")

    return {"result": job.result}


@router.get("/raw/send_netmiko_command")
async def send_netmiko_command(
    request: Request,
    host: str,
    device_type: str,
    command: str,
    credential_id: str,
    port: int = 22,
):
    queue = request.app.state.queue

    args = NetmikoSendCommandModel(
        host=host,
        device_type=device_type,
        command=command,
        credential_id=credential_id,
        port=port,
    )
    result = await queue.apply(
        "send_command_netmiko", timeout=10, json=args.model_dump_json()
    )
    return {"message": result}


@router.get("/raw/send_scrapli_command")
async def send_scrapli_command(
    request: Request,
    host: str,
    device_type: str,
    command: str,
    credential_id: str,
    port: int = 22,
):
    queue = request.app.state.queue

    args = ScrapliSendCommandModel(
        host=host,
        device_type=device_type,
        command=command,
        credential_id=credential_id,
        port=port,
    )
    result = await queue.apply(
        "send_command_scrapli", timeout=10, json=args.model_dump_json()
    )
    return {"message": result}


@router.get("/inventory/{device_name}")
async def inventory(
    device_name: str, inventory_store: InventoryStore = Depends(get_inventory_store)
) -> DeviceConfig:
    return inventory_store.get_device_config(device_name)


@router.get("/device/{device_name}/send_command")
async def send_inventory_command(
    request: Request,
    device_name: str,
    command: str,
    inventory_store: InventoryStore = Depends(get_inventory_store),
) -> dict[Literal["message"], str]:
    device_config = inventory_store.get_device_config(device_name)
    # credential = credential_store.get_ssh_credentials(device_config.credential_id)

    queue: saq.Queue = request.app.state.queue

    if device_config.adapter == "netmiko":
        args = NetmikoSendCommandModel(
            host=device_config.host,
            device_type=device_config.adapter_driver,
            command=command,
            credential_id=device_config.credential_id,
            port=device_config.port,
        )
        result = await queue.apply(
            "send_command_netmiko", timeout=10, json=args.model_dump_json()
        )

    elif device_config.adapter == "scrapli":
        args = ScrapliSendCommandModel(
            host=device_config.host,
            device_type=device_config.adapter_driver,
            command=command,
            credential_id=device_config.credential_id,
            port=device_config.port,
        )
        result = await queue.apply(
            "send_command_scrapli", timeout=10, json=args.model_dump_json()
        )

    else:
        raise TomException(f"Unknown device type {type(device_config)}")

    return {"message": result}
