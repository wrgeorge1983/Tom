import logging
from dataclasses import dataclass
from typing import List, Optional, Union

import saq
from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse
from starlette.requests import Request

from tom_shared.models import NetmikoSendCommandModel, ScrapliSendCommandModel
from tom_shared.models.models import InlineSSHCredential, StoredCredential
from tom_controller.api.helpers import enqueue_job
from tom_controller.api.inventory import get_inventory_store
from tom_controller.api.models import (
    JobResponse,
    SendCommandRequest,
    SendCommandsRequest,
    CommandSpec,
)
from tom_controller.exceptions import (
    TomNotFoundException,
    TomException,
)
from tom_controller.inventory.inventory import InventoryStore, DeviceConfig
from tom_controller.parsing import parse_output

logger = logging.getLogger(__name__)

router = APIRouter(tags=["device"])


# -----------------------------------------------------------------------------
# Helper functions for response handling
# -----------------------------------------------------------------------------


def _extract_error_message(error: str | None) -> str:
    """Extract a clean error message from a traceback string."""
    if not error:
        return "Command execution failed"
    error_lines = error.strip().split("\n")
    if error_lines:
        return error_lines[-1]
    return "Command execution failed"


def _error_response(
    message: str, status_code: int, raw_output: bool
) -> Union[PlainTextResponse, None]:
    """Return PlainTextResponse if raw_output mode, otherwise return None to signal raise."""
    if raw_output:
        return PlainTextResponse(content=message, status_code=status_code)
    return None


def _raise_or_plain(
    message: str,
    status_code: int,
    raw_output: bool,
    exception_class: type = TomException,
) -> PlainTextResponse:
    """Either raise an exception or return a PlainTextResponse based on raw_output mode."""
    if raw_output:
        return PlainTextResponse(content=message, status_code=status_code)
    raise exception_class(message)


# -----------------------------------------------------------------------------
# Job execution helper
# -----------------------------------------------------------------------------


@dataclass
class JobExecutionParams:
    """Parameters for executing a command job."""

    queue: saq.Queue
    device_config: DeviceConfig
    commands: List[str]
    credential: Union[StoredCredential, InlineSSHCredential]
    use_cache: bool
    cache_refresh: bool
    cache_ttl: Optional[int]
    wait: bool
    timeout: int
    retries: int = 3
    max_queue_wait: int = 300


async def _execute_device_job(
    params: JobExecutionParams,
    device_name: str,
    raw_output: bool,
) -> Union[JobResponse, PlainTextResponse]:
    """Execute a job on a device, handling adapter selection and error responses.

    Returns JobResponse on success, or PlainTextResponse for errors in raw_output mode.
    Raises TomException for errors when not in raw_output mode.
    """
    adapter = params.device_config.adapter

    kwargs = {
        "host": params.device_config.host,
        "device_type": params.device_config.adapter_driver,
        "commands": params.commands,
        "credential": params.credential,
        "port": params.device_config.port,
        "use_cache": params.use_cache,
        "cache_refresh": params.cache_refresh,
        "cache_ttl": params.cache_ttl,
        "max_queue_wait": params.max_queue_wait,
    }

    if adapter == "netmiko":
        args = NetmikoSendCommandModel(**kwargs)
        job_function = "send_commands_netmiko"
    elif adapter == "scrapli":
        args = ScrapliSendCommandModel(**kwargs)
        job_function = "send_commands_scrapli"
    else:
        return _raise_or_plain(
            f"Unknown adapter type: {adapter}",
            500,
            raw_output,
        )

    try:
        response = await enqueue_job(
            params.queue,
            job_function,
            args,
            wait=params.wait,
            timeout=params.timeout,
            retries=params.retries,
            max_queue_wait=params.max_queue_wait,
        )
    except Exception as e:
        return _raise_or_plain(
            f"Failed to enqueue job for {device_name}: {e}",
            500,
            raw_output,
        )

    return response


def _handle_job_completion_logging(
    response: JobResponse, device_name: str, command_desc: str
) -> None:
    """Log job completion status."""
    if response.status == "FAILED":
        logger.error(
            f"Device {command_desc} FAILED for {device_name}: "
            f"{response.error[:200] if response.error else 'Unknown error'}"
        )
    elif response.status == "COMPLETE":
        logger.info(
            f"Device {command_desc} completed for {device_name} after "
            f"{response.attempts} attempt(s)"
        )


def _format_raw_output_single(response: JobResponse, command: str) -> PlainTextResponse:
    """Format response as plain text for a single command."""
    output = response.get_command_output(command)
    return PlainTextResponse(content=output or "")


def _format_raw_output_multi(
    response: JobResponse, commands: List[str]
) -> PlainTextResponse:
    """Format response as plain text for multiple commands."""
    command_data = response.command_data
    if command_data:
        outputs = []
        for cmd in commands:
            output = command_data.get(cmd, "")
            outputs.append(f"### {cmd} ###\n{output}")
        return PlainTextResponse(content="\n\n".join(outputs))
    return PlainTextResponse(content="")


# -----------------------------------------------------------------------------
# API Endpoints
# -----------------------------------------------------------------------------


@router.post("/device/{device_name}/send_command", response_model=None)
async def send_inventory_command(
    request: Request,
    device_name: str,
    body: SendCommandRequest,
    inventory_store: InventoryStore = Depends(get_inventory_store),
) -> Union[JobResponse, PlainTextResponse]:
    """Send a single command to a device from inventory.

    By default, returns a JobResponse envelope containing:
    - job_id: Unique identifier for the job
    - status: Job status (QUEUED, COMPLETE, FAILED, etc.)
    - result: When complete, contains {"data": {...}, "meta": {...}}
    - attempts: Number of execution attempts
    - error: Error message if failed

    When wait=true and parse=true, the command output in result.data will be
    the parsed structured data instead of raw text.

    **Raw Output Mode** (raw_output=true):
    Opts out of the JobResponse envelope entirely. Returns plain text
    (text/plain) with just the device output. Requires wait=true.
    Errors return appropriate HTTP status codes with plain text messages:
    - 404: Device not found
    - 500: Queue/adapter errors
    - 502: Device command execution failed
    """
    logger.info(f"Device command request: {device_name} - {body.command[:50]}...")

    # Get device config
    device_config = inventory_store.get_device_config(device_name)
    if device_config is None:
        return _raise_or_plain(
            f"Device '{device_name}' not found in inventory",
            404,
            body.raw_output,
            TomNotFoundException,
        )

    # Build credential
    if body.username is not None and body.password is not None:
        credential: Union[StoredCredential, InlineSSHCredential] = InlineSSHCredential(
            username=body.username, password=body.password
        )
    else:
        credential = StoredCredential(credential_id=device_config.credential_id)

    # Execute job
    params = JobExecutionParams(
        queue=request.app.state.queue,
        device_config=device_config,
        commands=[body.command],
        credential=credential,
        use_cache=body.use_cache,
        cache_refresh=body.cache_refresh,
        cache_ttl=body.cache_ttl,
        wait=body.wait,
        timeout=body.timeout,
    )

    result = await _execute_device_job(params, device_name, body.raw_output)

    # If we got a PlainTextResponse (error in raw_output mode), return it
    if isinstance(result, PlainTextResponse):
        return result

    response = result

    # Handle completed job
    if body.wait:
        _handle_job_completion_logging(response, device_name, "command")

        # Check for failure in raw_output mode
        if response.status == "FAILED" and body.raw_output:
            return PlainTextResponse(
                content=_extract_error_message(response.error),
                status_code=502,
            )

        # Raw output mode - return plain text
        if body.raw_output:
            return _format_raw_output_single(response, body.command)

        # Parse mode - parse and wrap in JobResponse
        if body.parse and response.status == "COMPLETE":
            raw_output = response.get_command_output(body.command) or ""
            parsed_result = parse_output(
                raw_output=raw_output,
                settings=request.app.state.settings,
                device_type=device_config.adapter_driver,
                command=body.command,
                template=body.template,
                include_raw=body.include_raw,
                parser_type=body.parser,
            )
            return response.with_parsed_result({body.command: parsed_result})

    return response


@router.post("/device/{device_name}/send_commands", response_model=None)
async def send_inventory_commands(
    request: Request,
    device_name: str,
    body: SendCommandsRequest,
    inventory_store: InventoryStore = Depends(get_inventory_store),
) -> Union[JobResponse, PlainTextResponse]:
    """Send multiple commands to a device with per-command parsing configuration.

    By default, returns a JobResponse envelope containing:
    - job_id: Unique identifier for the job
    - status: Job status (QUEUED, COMPLETE, FAILED, etc.)
    - result: When complete, contains {"data": {...}, "meta": {...}}
    - attempts: Number of execution attempts
    - error: Error message if failed

    **Raw Output Mode** (raw_output=true):
    Opts out of the JobResponse envelope entirely. Returns plain text
    (text/plain) with all command outputs concatenated (separated by newlines).
    Requires wait=true. Errors return appropriate HTTP status codes with
    plain text messages:
    - 404: Device not found
    - 500: Queue/adapter errors
    - 502: Device command execution failed

    This endpoint supports both simple and advanced command execution:

    1. Simple mode: Pass a list of command strings
    2. Advanced mode: Pass CommandSpec objects with per-command parsing config

    Examples:
        Simple (all commands use same settings):
        ```json
        {
            "commands": ["show version", "show ip int brief"],
            "wait": true,
            "parse": true
        }
        ```

        Advanced (per-command control):
        ```json
        {
            "commands": [
                {
                    "command": "show version",
                    "parse": true,
                    "template": "custom_version.textfsm"
                },
                {
                    "command": "show ip int brief",
                    "parse": true
                },
                {
                    "command": "show running-config",
                    "parse": false
                }
            ],
            "wait": true
        }
        ```

        Raw output mode:
        ```json
        {
            "commands": ["show version", "show ip int brief"],
            "wait": true,
            "raw_output": true
        }
        ```
    """
    # Get device config
    device_config = inventory_store.get_device_config(device_name)
    if device_config is None:
        return _raise_or_plain(
            f"Device '{device_name}' not found in inventory",
            404,
            body.raw_output,
            TomNotFoundException,
        )

    # Build credential
    if body.username is not None and body.password is not None:
        credential: Union[StoredCredential, InlineSSHCredential] = InlineSSHCredential(
            username=body.username, password=body.password
        )
    else:
        credential = StoredCredential(credential_id=device_config.credential_id)

    # Normalize commands
    normalized_commands = body.get_normalized_commands()
    command_strings = [cmd.command for cmd in normalized_commands]
    command_specs_map = {cmd.command: cmd for cmd in normalized_commands}

    # Execute job
    params = JobExecutionParams(
        queue=request.app.state.queue,
        device_config=device_config,
        commands=command_strings,
        credential=credential,
        use_cache=body.use_cache,
        cache_refresh=body.cache_refresh,
        cache_ttl=body.cache_ttl,
        wait=body.wait,
        timeout=body.timeout,
        retries=body.retries,
        max_queue_wait=body.max_queue_wait,
    )

    result = await _execute_device_job(params, device_name, body.raw_output)

    # If we got a PlainTextResponse (error in raw_output mode), return it
    if isinstance(result, PlainTextResponse):
        return result

    response = result

    # Handle completed job
    if body.wait:
        _handle_job_completion_logging(response, device_name, "commands")

        # Check for failure in raw_output mode
        if response.status == "FAILED" and body.raw_output:
            return PlainTextResponse(
                content=_extract_error_message(response.error),
                status_code=502,
            )

        # Raw output mode - return concatenated plain text
        if body.raw_output:
            return _format_raw_output_multi(response, command_strings)

        # Parse mode - parse requested commands and wrap in JobResponse
        if response.status == "COMPLETE":
            commands_to_parse = [cmd for cmd in normalized_commands if cmd.parse]

            if commands_to_parse:
                parsed_results = {}
                command_data = response.command_data

                if command_data:
                    for command_str, raw_output in command_data.items():
                        cmd_spec = command_specs_map.get(command_str)

                        if cmd_spec and cmd_spec.parse and isinstance(raw_output, str):
                            parsed_results[command_str] = parse_output(
                                raw_output=raw_output,
                                settings=request.app.state.settings,
                                device_type=device_config.adapter_driver,
                                command=command_str,
                                template=cmd_spec.template,
                                include_raw=cmd_spec.include_raw or False,
                                parser_type=cmd_spec.parser or "textfsm",
                            )
                        else:
                            parsed_results[command_str] = raw_output

                return response.with_parsed_result(parsed_results)

    return response
