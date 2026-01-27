from typing import Union

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse
from starlette.requests import Request

from tom_shared.models import NetmikoSendCommandModel, ScrapliSendCommandModel
from tom_shared.models.models import StoredCredential, InlineSSHCredential
from tom_controller.api.helpers import enqueue_job
from tom_controller.api.models import JobResponse, RawCommandRequest
from tom_controller.exceptions import TomAuthException, TomException
from tom_controller.parsing import parse_output

router = APIRouter(tags=["raw"])


def _extract_error_message(error: str | None) -> str:
    """Extract a clean error message from a traceback string."""
    if not error:
        return "Command execution failed"
    error_lines = error.strip().split("\n")
    if error_lines:
        return error_lines[-1]
    return "Command execution failed"


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


@router.post("/raw/send_netmiko_command", response_model=None)
async def send_netmiko_command(
    request: Request,
    body: RawCommandRequest,
) -> Union[JobResponse, PlainTextResponse]:
    """Send a command to a device using Netmiko (no inventory lookup).

    This endpoint bypasses inventory and connects directly to the specified host.
    You must provide either `credential_id` (for stored credentials) or
    `username` + `password` (for inline credentials).

    **Response Modes:**
    - Default: Returns `JobResponse` envelope with job status and results
    - `raw_output=true`: Returns plain text device output (requires `wait=true`)
    - `parse=true`: Parses output using TextFSM or TTP templates

    **Parsing:**
    When `parse=true`, you can specify:
    - `parser`: "textfsm" (default) or "ttp"
    - `template`: Explicit template filename, or auto-discover based on device_type/command
    - `include_raw`: Include raw output alongside parsed result
    """
    if body.credential_id is None:
        if body.username is None or body.password is None:
            return _raise_or_plain(
                "Must provide either credential_id or username and password",
                400,
                body.raw_output,
                TomAuthException,
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
        return _raise_or_plain(
            f"Failed to enqueue job: {e}",
            500,
            body.raw_output,
        )

    # Handle completed job
    if body.wait:
        if response.status == "FAILED":
            if body.raw_output:
                return PlainTextResponse(
                    content=_extract_error_message(response.error),
                    status_code=502,
                )

        # Raw output mode
        if body.raw_output:
            output = response.get_command_output(body.command)
            return PlainTextResponse(content=output or "")

        # Parse mode
        if body.parse and response.status == "COMPLETE":
            raw_output = response.get_command_output(body.command) or ""
            parsed_result = parse_output(
                raw_output=raw_output,
                settings=request.app.state.settings,
                device_type=body.device_type,
                command=body.command,
                template=body.template,
                include_raw=body.include_raw,
                parser_type=body.parser,
            )
            return response.with_parsed_result({body.command: parsed_result})

    return response


@router.post("/raw/send_scrapli_command", response_model=None)
async def send_scrapli_command(
    request: Request,
    body: RawCommandRequest,
) -> Union[JobResponse, PlainTextResponse]:
    """Send a command to a device using Scrapli (no inventory lookup).

    This endpoint bypasses inventory and connects directly to the specified host.
    You must provide either `credential_id` (for stored credentials) or
    `username` + `password` (for inline credentials).

    **Response Modes:**
    - Default: Returns `JobResponse` envelope with job status and results
    - `raw_output=true`: Returns plain text device output (requires `wait=true`)
    - `parse=true`: Parses output using TextFSM or TTP templates

    **Parsing:**
    When `parse=true`, you can specify:
    - `parser`: "textfsm" (default) or "ttp"
    - `template`: Explicit template filename, or auto-discover based on device_type/command
    - `include_raw`: Include raw output alongside parsed result
    """
    if body.credential_id is None:
        if body.username is None or body.password is None:
            return _raise_or_plain(
                "Must provide either credential_id or username and password",
                400,
                body.raw_output,
                TomAuthException,
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
        return _raise_or_plain(
            f"Failed to enqueue job: {e}",
            500,
            body.raw_output,
        )

    # Handle completed job
    if body.wait:
        if response.status == "FAILED":
            if body.raw_output:
                return PlainTextResponse(
                    content=_extract_error_message(response.error),
                    status_code=502,
                )

        # Raw output mode
        if body.raw_output:
            output = response.get_command_output(body.command)
            return PlainTextResponse(content=output or "")

        # Parse mode
        if body.parse and response.status == "COMPLETE":
            raw_output = response.get_command_output(body.command) or ""
            parsed_result = parse_output(
                raw_output=raw_output,
                settings=request.app.state.settings,
                device_type=body.device_type,
                command=body.command,
                template=body.template,
                include_raw=body.include_raw,
                parser_type=body.parser,
            )
            return response.with_parsed_result({body.command: parsed_result})

    return response
