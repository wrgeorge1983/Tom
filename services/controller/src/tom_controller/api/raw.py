from typing import Optional

from fastapi import APIRouter, Query
from starlette.requests import Request

from tom_shared.models import NetmikoSendCommandModel, ScrapliSendCommandModel
from tom_shared.models.models import StoredCredential, InlineSSHCredential
from tom_controller.api.helpers import enqueue_job
from tom_controller.api.models import JobResponse, RawCommandRequest
from tom_controller.exceptions import TomAuthException

router = APIRouter(tags=["raw"])


@router.get("/raw/send_netmiko_command", deprecated=True)
async def send_netmiko_command_get(
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
    """DEPRECATED: Use POST /raw/send_netmiko_command instead."""
    if credential_id is None:
        if username is None and password is None:
            raise TomAuthException(
                "Must provide either credential_id or username and password"
            )

    if credential_id:
        credential = StoredCredential(credential_id=credential_id)
    else:
        credential = InlineSSHCredential(username=username, password=password)

    queue = request.app.state.queue

    commands = [command]
    args = NetmikoSendCommandModel(
        host=host,
        device_type=device_type,
        commands=commands,
        credential=credential,
        port=port,
    )
    return await enqueue_job(queue, "send_command_netmiko", args, wait=wait)


@router.post("/raw/send_netmiko_command")
async def send_netmiko_command(
    request: Request,
    body: RawCommandRequest,
) -> JobResponse:
    """Send a command to a device using Netmiko (no inventory lookup)."""
    if body.credential_id is None:
        if body.username is None or body.password is None:
            raise TomAuthException(
                "Must provide either credential_id or username and password"
            )

    if body.credential_id:
        credential = StoredCredential(credential_id=body.credential_id)
    else:
        credential = InlineSSHCredential(username=body.username, password=body.password)

    queue = request.app.state.queue

    args = NetmikoSendCommandModel(
        host=body.host,
        device_type=body.device_type,
        commands=[body.command],
        credential=credential,
        port=body.port,
    )
    return await enqueue_job(queue, "send_command_netmiko", args, wait=body.wait)


@router.get("/raw/send_scrapli_command", deprecated=True)
async def send_scrapli_command_get(
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
    """DEPRECATED: Use POST /raw/send_scrapli_command instead."""
    assert (credential_id is not None) ^ (
        username is not None and password is not None
    ), "Must provide either credential_id or username and password, not both"

    if credential_id:
        credential = StoredCredential(credential_id=credential_id)
    else:
        credential = InlineSSHCredential(username=username, password=password)

    queue = request.app.state.queue

    commands = [command]

    args = ScrapliSendCommandModel(
        host=host,
        device_type=device_type,
        commands=commands,
        credential=credential,
        port=port,
    )

    return await enqueue_job(queue, "send_command_scrapli", args, wait=wait)


@router.post("/raw/send_scrapli_command")
async def send_scrapli_command(
    request: Request,
    body: RawCommandRequest,
) -> JobResponse:
    """Send a command to a device using Scrapli (no inventory lookup)."""
    if body.credential_id is None:
        if body.username is None or body.password is None:
            raise TomAuthException(
                "Must provide either credential_id or username and password"
            )

    if body.credential_id:
        credential = StoredCredential(credential_id=body.credential_id)
    else:
        credential = InlineSSHCredential(username=body.username, password=body.password)

    queue = request.app.state.queue

    args = ScrapliSendCommandModel(
        host=body.host,
        device_type=body.device_type,
        commands=[body.command],
        credential=credential,
        port=body.port,
    )

    return await enqueue_job(queue, "send_command_scrapli", args, wait=body.wait)
