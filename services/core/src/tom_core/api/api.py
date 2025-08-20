import logging
from typing import Optional, TypedDict, Literal

from fastapi import APIRouter, Depends, Request, Query
from pydantic import BaseModel
import saq

from tom_core.api.models import JobResponse
from tom_shared.models import NetmikoSendCommandModel, ScrapliSendCommandModel
from tom_core.exceptions import TomException
from tom_core.inventory.inventory import (
    InventoryStore,
    DeviceConfig,
)
from tom_shared.models.models import StoredCredential, InlineSSHCredential




def get_inventory_store(request: Request) -> InventoryStore:
    return request.app.state.inventory_store


class AuthResponse(TypedDict):
    method: Literal["api_key", "None"]
    user: str | None

def api_key_auth(request: Request) -> AuthResponse:
    valid_headers = request.app.state.settings.api_key_headers
    valid_api_keys = request.app.state.settings.api_keys

    for header in valid_headers:
        api_key = request.headers.get(header)
        if api_key in valid_api_keys:
            return {"method": "api_key", "user": valid_api_keys[api_key]}

    header_keys = ", ".join(valid_headers)

    raise TomException(f"Missing api key header. One of: [{header_keys}]")

async def do_auth(request: Request) -> AuthResponse:
    settings = request.app.state.settings
    if settings.auth_mode == "none":
        return {"method": "None", "user": None}
    if settings.auth_mode == "api_key":
        return api_key_auth(request)
    else:
        raise TomException(f"Unknown auth mode {settings.auth_mode}")


class AuthRouter(APIRouter):
    auth_dep = Depends(do_auth)

    def __init__(self, *args, **kwargs):
        default_dependencies = kwargs.get("dependencies", [])
        kwargs["dependencies"] = [self.auth_dep] + default_dependencies
        super().__init__(*args, **kwargs)


async def enqueue_job(
    queue: saq.Queue,
    function_name: str,
    args: BaseModel,
    wait: bool = False,
    timeout: int = 10,
) -> JobResponse:
    job = await queue.enqueue(
        function_name,
        timeout=timeout,
        json=args.model_dump_json(),
        retries=5,
        retry_delay=1.0,
        retry_backoff=True,
    )
    if wait:
        await job.refresh(until_complete=float(timeout))

    job_response = JobResponse.from_job(job)
    return job_response


router = AuthRouter()


@router.get("/")
async def root():
    return {"message": "Hello World"}


@router.get("/foo")
async def foo(request: Request) -> JobResponse:
    queue: saq.Queue = request.app.state.queue
    return JobResponse.from_job(job)


@router.get("/job/{job_id}")
async def job(request: Request, job_id: str) -> Optional[JobResponse]:
    queue: saq.Queue = request.app.state.queue
    job = await JobResponse.from_job_id(job_id, queue)
    if job.status == "NEW":
        return None
    return job


@router.get("/raw/send_netmiko_command")
async def send_netmiko_command(
    request: Request,
    host: str,
    device_type: str,
    command: str,
    port: int = 22,
    wait: bool = False,
    # Stored Credentials
    credential_id: Optional[str] = None,
    # Inline SSH Credentials
    username: Optional[str] = None,
    password: Optional[str] = None,
) -> JobResponse:
    assert (credential_id is not None) ^ (
        username is not None and password is not None
    ), "Must provide either credential_id or username and password, not both"

    if credential_id:
        credential = StoredCredential(credential_id=credential_id)
    else:
        credential = InlineSSHCredential(username=username, password=password)

    queue = request.app.state.queue

    args = NetmikoSendCommandModel(
        host=host,
        device_type=device_type,
        command=command,
        credential=credential,
        port=port,
    )
    return await enqueue_job(queue, "send_command_netmiko", args, wait=wait)


@router.get("/raw/send_scrapli_command")
async def send_scrapli_command(
    request: Request,
    host: str,
    device_type: str,
    command: str,
    port: int = 22,
    wait: bool = False,
    # Stored Credentials
    credential_id: Optional[str] = Query(
        None,
        description="Stored credential ID. Must provide either credential_id or "
        "username and password, not both.",
    ),
    # Inline SSH Credentials
    username: Optional[str] = Query(
        None,
        description="SSH Username (requires password). Must provide either "
        "credential_id or username and password, not both.",
    ),
    password: Optional[str] = Query(
        None,
        description="SSH Password (requires username). Must provide either "
        "credential_id or username and password, not both.",
    ),
) -> JobResponse:
    assert (credential_id is not None) ^ (
        username is not None and password is not None
    ), "Must provide either credential_id or username and password, not both"

    if credential_id:
        credential = StoredCredential(credential_id=credential_id)
    else:
        credential = InlineSSHCredential(username=username, password=password)

    queue = request.app.state.queue

    args = ScrapliSendCommandModel(
        host=host,
        device_type=device_type,
        command=command,
        credential=credential,
        port=port,
    )

    return await enqueue_job(queue, "send_command_scrapli", args, wait=wait)


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
    wait: bool = False,
    rawOutput: bool = Query(False, description="Return raw output directly. Only works with wait=True"),
    timeout: int = 10,
    # Optional Inline SSH Credentials
    username: Optional[str] = Query(
        None,
        description="Override username (requires password). Uses inventory "
        "credential if not provided.",
    ),
    password: Optional[str] = Query(
        None,
        description="Override password (requires username). Uses inventory "
        "credential if not provided.",
    ),
) -> JobResponse | str:
    device_config = inventory_store.get_device_config(device_name)


    if username is not None and password is not None:
        credential = InlineSSHCredential(username=username, password=password)
    else:
        credential = StoredCredential(credential_id=device_config.credential_id)

    queue: saq.Queue = request.app.state.queue

    if device_config.adapter == "netmiko":
        args = NetmikoSendCommandModel(
            host=device_config.host,
            device_type=device_config.adapter_driver,
            command=command,
            credential=credential,
            port=device_config.port,
        )
        try:
            response = await enqueue_job(
                queue, "send_command_netmiko", args, wait=wait, timeout=timeout
            )
        except Exception as e:
            raise TomException(f"Failed to enqueue job for {device_name}: {e}")

    elif device_config.adapter == "scrapli":
        args = ScrapliSendCommandModel(
            host=device_config.host,
            device_type=device_config.adapter_driver,
            command=command,
            credential=credential,
            port=device_config.port,
        )
        try:
            response = await enqueue_job(
                queue, "send_command_scrapli", args, wait=wait, timeout=timeout
            )
        except Exception as e:
            raise TomException(f"Failed to enqueue job for {device_name}: {e}")

    else:
        raise TomException(f"Unknown device type {type(device_config)}")

    if wait:
        if rawOutput:
            response = response.result

    return response
