import logging
from typing import Optional

import saq
from fastapi import APIRouter, Depends, Query
from starlette.requests import Request

from tom_shared.models import NetmikoSendCommandModel, ScrapliSendCommandModel
from tom_shared.models.models import InlineSSHCredential, StoredCredential
from tom_controller.api.helpers import enqueue_job
from tom_controller.api.inventory import get_inventory_store
from tom_controller.api.models import (
    JobResponse,
    SendCommandRequest,
    SendCommandsRequest,
)
from tom_controller.exceptions import (
    TomNotFoundException,
    TomException,
    TomValidationException,
)
from tom_controller.inventory.inventory import InventoryStore
from tom_controller.parsing import parse_output

logger = logging.getLogger(__name__)

router = APIRouter(tags=["device"])


@router.get("/device/{device_name}/send_command", deprecated=True)
async def send_inventory_command_get(
    request: Request,
    device_name: str,
    command: str,
    inventory_store: InventoryStore = Depends(get_inventory_store),
    wait: bool = False,
    rawOutput: bool = Query(
        False, description="Return raw output directly. Only works with wait=True"
    ),
    parse: bool = Query(
        False,
        description="Parse output using specified parser. Only works with wait=True",
    ),
    parser: str = Query("textfsm", description="Parser to use ('textfsm' or 'ttp')"),
    template: Optional[str] = Query(
        None, description="Template name (e.g., 'cisco_ios_show_ip_int_brief.textfsm')"
    ),
    include_raw: bool = Query(
        False, description="Include raw output along with parsed (when parse=True)"
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
    use_cache: bool = Query(
        False, description="This job is eligible for caching. Only works with wait=True"
    ),
    cache_ttl: Optional[int] = Query(
        None, description="Cache TTL in seconds. Only works with wait=True"
    ),
    cache_refresh: bool = Query(
        False, description="Force refresh cached result. Only works with wait=True"
    ),
) -> JobResponse | str | dict:
    logger.info(f"Device command request: {device_name} - {command[:50]}...")
    device_config = inventory_store.get_device_config(device_name)
    if device_config is None:
        raise TomNotFoundException(f"Device '{device_name}' not found in inventory")

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
            use_cache=use_cache,
            cache_refresh=cache_refresh,
            cache_ttl=cache_ttl,
        )
        try:
            response = await enqueue_job(
                queue, "send_commands_netmiko", args, wait=wait, timeout=timeout
            )
        except Exception as e:
            raise TomException(f"Failed to enqueue job for {device_name}: {e}") from e

    elif device_config.adapter == "scrapli":
        args = ScrapliSendCommandModel(
            host=device_config.host,
            device_type=device_config.adapter_driver,
            commands=commands,
            credential=credential,
            port=device_config.port,
            use_cache=use_cache,
            cache_refresh=cache_refresh,
            cache_ttl=cache_ttl,
        )
        try:
            response = await enqueue_job(
                queue, "send_commands_scrapli", args, wait=wait, timeout=timeout
            )
        except Exception as e:
            raise TomException(f"Failed to enqueue job for {device_name}: {e}") from e

    else:
        raise TomException(f"Unknown device type {type(device_config)}")

    if wait:
        # Log the result status
        if response.status == "FAILED":
            logger.error(
                f"Device command FAILED for {device_name}: {response.error[:200] if response.error else 'Unknown error'}"
            )
        elif response.status == "COMPLETE":
            logger.info(
                f"Device command completed for {device_name} after {response.attempts} attempt(s)"
            )

        # Handle parsing if requested
        if parse and not rawOutput:
            if parser not in ["textfsm", "ttp"]:
                raise TomValidationException(
                    f"Parser '{parser}' not supported. Use 'textfsm' or 'ttp'"
                )

            raw_output = response.get_command_output(command) or ""

            # Parse the output using shared function

            parsed_result = parse_output(
                raw_output=raw_output,
                settings=request.app.state.settings,
                device_type=device_config.adapter_driver,
                command=command,
                template=template,
                include_raw=include_raw,
                parser_type=parser,
            )

            return parsed_result

        elif rawOutput:
            output = response.get_command_output(command)
            if output is None:
                return ""  # Return empty string instead of None
            return output

    # If there's cache metadata and we're returning the full response, include it
    if isinstance(response, JobResponse) and response.cache_metadata:
        # Add cache metadata to the response for visibility
        response_dict = response.model_dump()
        response_dict["_cache"] = response.cache_metadata
        return response_dict

    return response


@router.post("/device/{device_name}/send_command")
async def send_inventory_command(
    request: Request,
    device_name: str,
    body: SendCommandRequest,
    inventory_store: InventoryStore = Depends(get_inventory_store),
) -> JobResponse | str | dict:
    """Send a single command to a device from inventory."""
    logger.info(f"Device command request: {device_name} - {body.command[:50]}...")
    device_config = inventory_store.get_device_config(device_name)
    if device_config is None:
        raise TomNotFoundException(f"Device '{device_name}' not found in inventory")

    if body.username is not None and body.password is not None:
        credential = InlineSSHCredential(username=body.username, password=body.password)
    else:
        credential = StoredCredential(credential_id=device_config.credential_id)

    commands = [body.command]
    queue: saq.Queue = request.app.state.queue

    if device_config.adapter == "netmiko":
        args = NetmikoSendCommandModel(
            host=device_config.host,
            device_type=device_config.adapter_driver,
            commands=commands,
            credential=credential,
            port=device_config.port,
            use_cache=body.use_cache,
            cache_refresh=body.cache_refresh,
            cache_ttl=body.cache_ttl,
        )
        try:
            response = await enqueue_job(
                queue,
                "send_commands_netmiko",
                args,
                wait=body.wait,
                timeout=body.timeout,
            )
        except Exception as e:
            raise TomException(f"Failed to enqueue job for {device_name}: {e}") from e

    elif device_config.adapter == "scrapli":
        args = ScrapliSendCommandModel(
            host=device_config.host,
            device_type=device_config.adapter_driver,
            commands=commands,
            credential=credential,
            port=device_config.port,
            use_cache=body.use_cache,
            cache_refresh=body.cache_refresh,
            cache_ttl=body.cache_ttl,
        )
        try:
            response = await enqueue_job(
                queue,
                "send_commands_scrapli",
                args,
                wait=body.wait,
                timeout=body.timeout,
            )
        except Exception as e:
            raise TomException(f"Failed to enqueue job for {device_name}: {e}") from e

    else:
        raise TomException(f"Unknown adapter type: {device_config.adapter}")

    if body.wait:
        # Log the result status
        if response.status == "FAILED":
            logger.error(
                f"Device command FAILED for {device_name}: {response.error[:200] if response.error else 'Unknown error'}"
            )
        elif response.status == "COMPLETE":
            logger.info(
                f"Device command completed for {device_name} after {response.attempts} attempt(s)"
            )

        # Handle parsing if requested
        if body.parse:
            if body.parser not in ["textfsm", "ttp"]:
                raise TomValidationException(
                    f"Parser '{body.parser}' not supported. Use 'textfsm' or 'ttp'"
                )

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

            return parsed_result

    # If there's cache metadata and we're returning the full response, include it
    if isinstance(response, JobResponse) and response.cache_metadata:
        response_dict = response.model_dump()
        response_dict["_cache"] = response.cache_metadata
        return response_dict

    return response


@router.post("/device/{device_name}/send_commands")
async def send_inventory_commands(
    request: Request,
    device_name: str,
    body: SendCommandsRequest,
    inventory_store: InventoryStore = Depends(get_inventory_store),
) -> JobResponse | dict:
    """Send multiple commands to a device with per-command parsing configuration.

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
    """
    device_config = inventory_store.get_device_config(device_name)
    if device_config is None:
        raise TomNotFoundException(f"Device '{device_name}' not found in inventory")

    # Handle credentials
    if body.username is not None and body.password is not None:
        credential = InlineSSHCredential(username=body.username, password=body.password)
    else:
        credential = StoredCredential(credential_id=device_config.credential_id)

    queue: saq.Queue = request.app.state.queue

    # Get normalized commands (all as CommandSpec objects)
    normalized_commands = body.get_normalized_commands()

    # Extract just the command strings for execution
    command_strings = [cmd.command for cmd in normalized_commands]

    # Store command specs for parsing later
    command_specs_map = {cmd.command: cmd for cmd in normalized_commands}

    kwargs = {
        "host": device_config.host,
        "device_type": device_config.adapter_driver,
        "commands": command_strings,
        "credential": credential,
        "port": device_config.port,
        "use_cache": body.use_cache,
        "cache_refresh": body.cache_refresh,
        "cache_ttl": body.cache_ttl,
        "max_queue_wait": body.max_queue_wait,
    }

    if device_config.adapter == "netmiko":
        args = NetmikoSendCommandModel(**kwargs)
        try:
            response = await enqueue_job(
                queue,
                "send_commands_netmiko",
                args,
                wait=body.wait,
                timeout=body.timeout,
                retries=body.retries,
                max_queue_wait=body.max_queue_wait,
            )
        except Exception as e:
            raise TomException(f"Failed to enqueue job for {device_name}: {e}") from e

    elif device_config.adapter == "scrapli":
        args = ScrapliSendCommandModel(**kwargs)
        try:
            response = await enqueue_job(
                queue,
                "send_commands_scrapli",
                args,
                wait=body.wait,
                timeout=body.timeout,
                retries=body.retries,
                max_queue_wait=body.max_queue_wait,
            )
        except Exception as e:
            raise TomException(f"Failed to enqueue job for {device_name}: {e}") from e

    else:
        raise TomException(f"Unknown device type {type(device_config)}")

    # Handle parsing if requested and waiting
    if body.wait:
        # Check if any commands require parsing
        commands_to_parse = [cmd for cmd in normalized_commands if cmd.parse]

        if commands_to_parse and response.status == "COMPLETE":
            parsed_results = {}
            command_data = response.command_data

            if command_data:
                for command_str, raw_output in command_data.items():
                    cmd_spec = command_specs_map.get(command_str)

                    if cmd_spec and cmd_spec.parse and isinstance(raw_output, str):
                        # Parse this specific command with its own settings
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
                        # Return raw output for commands that don't need parsing
                        parsed_results[command_str] = raw_output

            # Include cache metadata if present
            result = {"data": parsed_results}
            if response.cache_metadata:
                result["_cache"] = response.cache_metadata

            return result

    return response
