import logging
from typing import Optional, TypedDict, Literal

from fastapi import APIRouter, Depends, Request, Query
from pydantic import BaseModel
import saq

from tom_controller.api.models import JobResponse
from tom_shared.models import NetmikoSendCommandModel, ScrapliSendCommandModel
from tom_controller.exceptions import (
    TomException,
    TomAuthException,
    TomNotFoundException,
)
from tom_controller.inventory.inventory import (
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
    valid_api_keys = request.app.state.settings.api_key_users

    for header in valid_headers:
        api_key = request.headers.get(header)
        if api_key in valid_api_keys:
            return {"method": "api_key", "user": valid_api_keys[api_key]}

    header_keys = ", ".join(f"'{header}'" for header in valid_headers)

    raise TomAuthException(
        f"Missing or invalid API key. Requires one of these headers: {header_keys}"
    )


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

    commands = [command]
    args = NetmikoSendCommandModel(
        host=host,
        device_type=device_type,
        commands=commands,
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

    commands = [command]

    args = ScrapliSendCommandModel(
        host=host,
        device_type=device_type,
        commands=commands,
        credential=credential,
        port=port,
    )

    return await enqueue_job(queue, "send_command_scrapli", args, wait=wait)


@router.get("/inventory/export")
async def export_inventory(
    inventory_store: InventoryStore = Depends(get_inventory_store),
    filter_name: Optional[str] = Query(
        None,
        description="Optional filter name (switches, routers, iosxe, arista_exclusion)",
    ),
) -> dict[str, DeviceConfig]:
    """Export all nodes from inventory in DeviceConfig format."""
    import logging

    log = logging.getLogger(__name__)
    log.info(f"Exporting inventory nodes with filter: {filter_name}")

    try:
        nodes = await inventory_store.alist_all_nodes()

        # Apply filter if specified
        if filter_name:
            from tom_controller.inventory.solarwinds import FilterRegistry

            filter_obj = FilterRegistry.get_filter(filter_name)
            nodes = [node for node in nodes if filter_obj.matches(node)]
            log.info(f"Filtered to {len(nodes)} nodes using {filter_name} filter")
        else:
            log.info(f"Exported {len(nodes)} nodes (no filter)")

        # Convert to DeviceConfig format
        device_configs = {}
        for node in nodes:
            caption = node.get("Caption")
            if caption:
                # For SWIS, convert node to DeviceConfig; for YAML, node is already in DeviceConfig format
                if hasattr(inventory_store, "_node_to_device_config"):
                    device_configs[caption] = inventory_store._node_to_device_config(
                        node
                    )
                else:
                    # YAML store - node already has DeviceConfig fields
                    device_configs[caption] = DeviceConfig(
                        **{k: v for k, v in node.items() if k != "Caption"}
                    )

        return device_configs
    except Exception as e:
        log.error(f"Failed to export inventory: {e}")
        raise


@router.get("/inventory/export/raw")
async def export_raw_inventory(
    inventory_store: InventoryStore = Depends(get_inventory_store),
    filter_name: Optional[str] = Query(
        None,
        description="Optional filter name (switches, routers, iosxe, arista_exclusion)",
    ),
) -> list[dict]:
    """Export raw nodes from inventory (SolarWinds format for SWIS, YAML format for YAML)."""
    import logging

    log = logging.getLogger(__name__)
    log.info(f"Exporting raw inventory nodes with filter: {filter_name}")

    try:
        nodes = await inventory_store.alist_all_nodes()

        # Apply filter if specified
        if filter_name:
            from tom_controller.inventory.solarwinds import FilterRegistry

            filter_obj = FilterRegistry.get_filter(filter_name)
            nodes = [node for node in nodes if filter_obj.matches(node)]
            log.info(f"Filtered to {len(nodes)} raw nodes using {filter_name} filter")
        else:
            log.info(f"Exported {len(nodes)} raw nodes (no filter)")

        return nodes
    except Exception as e:
        log.error(f"Failed to export raw inventory: {e}")
        raise


@router.get("/inventory/filters")
async def list_filters() -> dict[str, str]:
    """List available inventory filters."""
    from tom_controller.inventory.solarwinds import FilterRegistry

    return FilterRegistry.get_available_filters()


@router.get("/inventory/{device_name}")
async def inventory(
    device_name: str, inventory_store: InventoryStore = Depends(get_inventory_store)
) -> DeviceConfig:
    import logging

    log = logging.getLogger(__name__)
    log.info(f"Inventory endpoint called for device: {device_name}")
    log.info(f"Inventory store type: {type(inventory_store)}")

    try:
        result = await inventory_store.aget_device_config(device_name)
        log.info(f"Successfully retrieved config for {device_name}")
        return result
    except Exception as e:
        log.error(f"Failed to get device config for {device_name}: {e}")
        raise


@router.get("/device/{device_name}/send_command")
async def send_inventory_command(
    request: Request,
    device_name: str,
    command: str,
    inventory_store: InventoryStore = Depends(get_inventory_store),
    wait: bool = False,
    rawOutput: bool = Query(
        False, description="Return raw output directly. Only works with wait=True"
    ),
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

    commands = [command]
    queue: saq.Queue = request.app.state.queue

    if device_config.adapter == "netmiko":
        args = NetmikoSendCommandModel(
            host=device_config.host,
            device_type=device_config.adapter_driver,
            commands=commands,
            credential=credential,
            port=device_config.port,
        )
        try:
            response = await enqueue_job(
                queue, "send_commands_netmiko", args, wait=wait, timeout=timeout
            )
        except Exception as e:
            raise TomException(f"Failed to enqueue job for {device_name}: {e}")

    elif device_config.adapter == "scrapli":
        args = ScrapliSendCommandModel(
            host=device_config.host,
            device_type=device_config.adapter_driver,
            commands=commands,
            credential=credential,
            port=device_config.port,
        )
        try:
            response = await enqueue_job(
                queue, "send_commands_scrapli", args, wait=wait, timeout=timeout
            )
        except Exception as e:
            raise TomException(f"Failed to enqueue job for {device_name}: {e}")

    else:
        raise TomException(f"Unknown device type {type(device_config)}")

    if wait:
        if rawOutput:
            response = response.result.get(command)

    return response


@router.post("/device/{device_name}/send_commands")
async def send_inventory_commands(
    request: Request,
    device_name: str,
    commands: list[str],
    inventory_store: InventoryStore = Depends(get_inventory_store),
    wait: bool = False,
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
) -> JobResponse:
    device_config = inventory_store.get_device_config(device_name)
    if username is not None and password is not None:
        credential = InlineSSHCredential(username=username, password=password)
    else:
        credential = StoredCredential(credential_id=device_config.credential_id)

    queue: saq.Queue = request.app.state.queue

    kwargs = {
        "host": device_config.host,
        "device_type": device_config.adapter_driver,
        "commands": commands,
        "credential": credential,
        "port": device_config.port,
    }
    if device_config.adapter == "netmiko":
        args = NetmikoSendCommandModel(**kwargs)
        try:
            response = await enqueue_job(
                queue, "send_commands_netmiko", args, wait=wait
            )
        except Exception as e:
            raise TomException(f"Failed to enqueue job for {device_name}: {e}")

    elif device_config.adapter == "scrapli":
        args = ScrapliSendCommandModel(**kwargs)
        try:
            response = await enqueue_job(
                queue, "send_commands_scrapli", args, wait=wait
            )
        except Exception as e:
            raise TomException(f"Failed to enqueue job for {device_name}: {e}")

    else:
        raise TomException(f"Unknown device type {type(device_config)}")

    return response
