import logging
import os
import yaml
from datetime import datetime
from pathlib import Path
from typing import Optional, TypedDict, Literal, Dict, Any

from fastapi import APIRouter, Depends, Request, Query, HTTPException, Response
import httpx
from jose import jwt as jose_jwt
from jose.exceptions import JWTError
from pydantic import BaseModel
import saq
from saq import Status

from tom_controller.api.models import (
    JobResponse,
    SendCommandsRequest,
    SendCommandRequest,
    RawCommandRequest,
    CommandSpec,
)
from tom_controller.monitoring import MetricsExporter
from tom_controller.api import monitoring_api
from tom_shared.models import NetmikoSendCommandModel, ScrapliSendCommandModel

from tom_controller.config import settings as app_settings
from tom_controller.exceptions import (
    TomException,
    TomAuthException,
    TomAuthorizationException,
    TomNotFoundException,
    TomValidationException,
)
from tom_controller.inventory.inventory import (
    InventoryStore,
    DeviceConfig,
    InventoryFilter,
)
from tom_shared.models.models import StoredCredential, InlineSSHCredential
from tom_controller.auth import JWTValidationError, JWTValidator
from tom_controller.parsing import parse_output
from tom_controller.parsing.textfsm_parser import TextFSMParser

logger = logging.getLogger(__name__)


def get_inventory_store(request: Request) -> InventoryStore:
    return request.app.state.inventory_store


class AuthResponse(TypedDict):
    method: Literal["api_key", "jwt", "none"]
    user: str | None
    provider: Optional[str]
    claims: Optional[Dict[str, Any]]


def api_key_auth(request: Request) -> AuthResponse:
    valid_headers = request.app.state.settings.api_key_headers
    valid_api_keys = request.app.state.settings.api_key_users

    for header in valid_headers:
        api_key = request.headers.get(header)
        if api_key in valid_api_keys:
            return {
                "method": "api_key",
                "user": valid_api_keys[api_key],
                "provider": None,
                "claims": None,
            }

    header_keys = ", ".join(f"'{header}'" for header in valid_headers)

    raise TomAuthException(
        f"Missing or invalid API key. Requires one of these headers: {header_keys}"
    )


async def _jwt_auth(token: str, providers: list[JWTValidator]) -> AuthResponse:
    """Validate JWT against providers in order."""

    import re

    token_issuer = None

    try:
        unverified_claims = jose_jwt.get_unverified_claims(token)
        token_issuer = unverified_claims.get("iss")
        oauth_provider = next(
            provider for provider in providers if provider.issuer == token_issuer
        )
    except JWTError as e:
        logging.error(f"JWT validation failed: {e}")
        raise TomAuthException("Invalid JWT token - could not extract issuer") from e
    except StopIteration:
        logging.error(f"No matching provider found for issuer: {token_issuer}")
        raise TomAuthException("Invalid JWT token - issuer not found")

    logging.info(f"Token issuer (unverified): {token_issuer}")

    try:
        claims = await oauth_provider.validate_token(token)
        user = oauth_provider.get_user_identifier(claims)
    except JWTValidationError as e:
        logging.warning(
            f"JWT validation failed for provider {oauth_provider.name}: {e}"
        )
        raise TomAuthException("Invalid JWT token - could not validate token") from e
    finally:
        await oauth_provider.close()

    # Enforce simple allow policy for JWT-authenticated users.
    # Precedence: allowed_users > allowed_domains > allowed_user_regex
    allowed_users = [u.lower() for u in app_settings.allowed_users]
    allowed_domains = [d.lower() for d in app_settings.allowed_domains]
    allowed_user_regex = app_settings.allowed_user_regex or []

    if allowed_users or allowed_domains or allowed_user_regex:
        canonical_user = (user or "").lower()

        # 1) Exact user allowlist
        if allowed_users and canonical_user in allowed_users:
            pass  # allowed
        else:
            # Determine email-like identifier for domain matching
            email_like = None
            for k in ("email", "preferred_username", "upn"):
                v = claims.get(k)
                if isinstance(v, str) and "@" in v:
                    email_like = v
                    break

            # 2) Domain allowlist
            domain_ok = False
            if allowed_domains and email_like:
                domain = email_like.split("@")[-1].lower()
                domain_ok = domain in allowed_domains

            if not domain_ok:
                # 3) Regex against canonical user, then email if present
                regex_ok = False
                if allowed_user_regex:
                    regex_ok = any(
                        re.search(p, canonical_user, flags=re.IGNORECASE)
                        for p in allowed_user_regex
                    ) or (
                        isinstance(email_like, str)
                        and any(
                            re.search(p, email_like, flags=re.IGNORECASE)
                            for p in allowed_user_regex
                        )
                    )

                if not regex_ok:
                    raise TomAuthorizationException(
                        f"Access denied: {canonical_user=} not permitted by policy"
                    )

    if app_settings.permit_logging_user_details:
        logging.info(
            f"JWT successfully validated by {oauth_provider.name} for user {user}"
        )
    else:
        logging.info(f"JWT successfully validated by {oauth_provider.name}")

    return {
        "method": "jwt",
        "user": user,
        "provider": oauth_provider.name,
        "claims": claims,
    }


async def jwt_auth(request: Request) -> AuthResponse:
    """Validate JWT from Authorization header."""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise TomAuthException("Missing or invalid Bearer token")

    token = auth_header[7:]  # Remove "Bearer " prefix

    # Debug: Log token prefix only when PII logging is permitted
    if app_settings.permit_logging_user_details:
        logging.info(f"Attempting JWT validation with token starting: {token[:50]}...")
    else:
        logging.info("Attempting JWT validation")

    # Check HTTPS requirement
    settings = request.app.state.settings
    if settings.jwt_require_https:
        # Check if connection is secure
        if request.url.scheme != "https":
            # Allow localhost for development
            if request.client and request.client.host not in [
                "127.0.0.1",
                "localhost",
                "::1",
            ]:
                raise TomAuthException("JWT authentication requires HTTPS")

    return await _jwt_auth(token, request.app.state.jwt_providers)


async def do_auth(request: Request) -> AuthResponse:
    settings = request.app.state.settings

    # Debug logging
    logging.info(f"Auth check - auth_mode: {settings.auth_mode}")

    if settings.auth_mode == "none":
        return {"method": "none", "user": None, "provider": None, "claims": None}

    # Try API key auth first in hybrid mode
    if settings.auth_mode in ["api_key", "hybrid"]:
        try:
            return api_key_auth(request)

        except TomAuthException:
            if settings.auth_mode == "api_key":
                raise
            # Continue to JWT check in hybrid mode

    # Try JWT auth
    if settings.auth_mode in ["jwt", "hybrid"]:
        return await jwt_auth(request)

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
    retries: int = 3,
    max_queue_wait: int = 300,
) -> JobResponse:
    logger.info(f"Enqueuing job: {function_name}")
    job = await queue.enqueue(
        function_name,
        timeout=timeout,
        json=args.model_dump_json(),
        retries=retries,
        retry_delay=1.0,
        retry_backoff=True,
    )
    logger.info(f"Enqueued job {job.id} with retries={job.retries}")

    if wait:
        await job.refresh(until_complete=float(timeout))
        # Log job completion status
        if job.status == Status.COMPLETE:
            logger.info(
                f"Job {job.id} completed successfully after {job.attempts} attempt(s)"
            )
        elif job.status == Status.FAILED:
            # Extract useful error info
            error_summary = None
            if job.error:
                # Look for our custom exception types in the error
                if "AuthenticationException" in job.error:
                    error_summary = "Authentication failed"
                elif "GatingException" in job.error:
                    error_summary = "Device busy"
                else:
                    # Get the last line of the traceback which usually has the actual error
                    error_lines = job.error.strip().split("\n")
                    if error_lines:
                        error_summary = error_lines[-1][:200]  # Limit length

            logger.error(
                f"Job {job.id} FAILED after {job.attempts} attempt(s) - {error_summary or 'Unknown error'}"
            )
        elif job.status == Status.ABORTED:
            logger.warning(f"Job {job.id} was aborted after {job.attempts} attempt(s)")
        else:
            logger.info(
                f"Job {job.id} status: {job.status} after {job.attempts} attempt(s)"
            )

    job_response = JobResponse.from_job(job)
    return job_response


router = AuthRouter()

# Unauthenticated router for Prometheus metrics
metrics_router = APIRouter()


@router.get("/")
async def root():
    return {"message": "Hello World"}


@router.get("/job/{job_id}")
async def job(
    request: Request,
    job_id: str,
    parse: bool = Query(False, description="Parse output using TextFSM"),
    parser: str = Query("textfsm", description="Parser to use"),
    template: Optional[str] = Query(None, description="Template name for parsing"),
    include_raw: bool = Query(False, description="Include raw output with parsed"),
) -> Optional[JobResponse | dict]:
    queue: saq.Queue = request.app.state.queue
    job_response = await JobResponse.from_job_id(job_id, queue)

    # Log job status check
    if job_response.status == "NEW":
        logger.debug(f"Job {job_id} not found or NEW")
        return None
    elif job_response.status == "COMPLETE":
        logger.info(
            f"Job {job_id} status check: COMPLETE after {job_response.attempts} attempt(s)"
        )
    elif job_response.status == "FAILED":
        # Extract error summary
        error_summary = None
        if job_response.error:
            if "AuthenticationException" in job_response.error:
                error_summary = "Authentication failed"
            elif "GatingException" in job_response.error:
                error_summary = "Device busy"
            else:
                error_lines = job_response.error.strip().split("\n")
                if error_lines:
                    error_summary = error_lines[-1][:200]
        logger.error(
            f"Job {job_id} status check: FAILED after {job_response.attempts} attempt(s) - {error_summary or 'Unknown error'}"
        )
    else:
        logger.info(f"Job {job_id} status check: {job_response.status}")

    # If parsing requested and job is complete with results
    if parse and job_response.status == "COMPLETE" and job_response.result:
        settings = request.app.state.settings

        # Extract device_type and commands from metadata
        device_type = None
        commands = None
        if job_response.metadata:
            device_type = job_response.metadata.get("device_type")
            commands = job_response.metadata.get("commands", [])

        # Parse each command result
        parsed_results = {}
        command_data = job_response.command_data
        if command_data:
            for command, raw_output in command_data.items():
                if isinstance(raw_output, str):
                    parsed_results[command] = parse_output(
                        raw_output=raw_output,
                        settings=settings,
                        device_type=device_type,
                        command=command,
                        template=template,
                        include_raw=include_raw,
                        parser_type=parser,
                    )
                else:
                    parsed_results[command] = raw_output
        else:
            # Single result, not a dict
            parsed_results = parse_output(
                raw_output=str(job_response.result),
                settings=settings,
                device_type=device_type,
                command=commands[0] if commands else None,
                template=template,
                include_raw=include_raw,
                parser_type=parser,
            )

        return parsed_results

    return job_response


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


@router.get("/inventory/export")
async def export_inventory(
    request: Request,
    inventory_store: InventoryStore = Depends(get_inventory_store),
    filter_name: Optional[str] = Query(
        None,
        description="Optional named filter (switches, routers, iosxe, arista_exclusion, ospf_crawler_filter)",
    ),
) -> dict[str, DeviceConfig]:
    """Export all nodes from inventory in DeviceConfig format.

    Supports two filtering modes:
    1. Named filters: ?filter_name=switches
    2. Inline filters: ?Caption=router.*&Vendor=cisco

    If filter_name is provided, it takes precedence over inline filters.
    Use GET /api/inventory/fields to see available filterable fields.
    Use GET /api/inventory/filters to see available named filters.
    """
    import logging

    log = logging.getLogger(__name__)

    try:
        nodes = await inventory_store.alist_all_nodes()

        # Apply named filter if specified
        if filter_name:
            filter_obj = inventory_store.get_filter(filter_name)
            nodes = [node for node in nodes if filter_obj.matches(node)]
            log.info(
                f"Filtered to {len(nodes)} nodes using named filter '{filter_name}'"
            )
        else:
            # Get all query params as inline filter patterns
            filter_params = dict(request.query_params)

            # Apply inline filters if any field patterns provided
            if filter_params:
                filter_obj = InventoryFilter(filter_params)
                nodes = [node for node in nodes if filter_obj.matches(node)]
                log.info(
                    f"Filtered to {len(nodes)} nodes using inline filters: {filter_params}"
                )
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
    request: Request,
    inventory_store: InventoryStore = Depends(get_inventory_store),
    filter_name: Optional[str] = Query(
        None,
        description="Optional named filter (switches, routers, iosxe, arista_exclusion, ospf_crawler_filter)",
    ),
) -> list[dict]:
    """Export raw nodes from inventory (SolarWinds format for SWIS, YAML format for YAML).

    Supports two filtering modes:
    1. Named filters: ?filter_name=switches
    2. Inline filters: ?Vendor=cisco&Description=asr.*

    If filter_name is provided, it takes precedence over inline filters.
    Use GET /api/inventory/fields to see available filterable fields.
    Use GET /api/inventory/filters to see available named filters.
    """
    import logging

    log = logging.getLogger(__name__)

    try:
        nodes = await inventory_store.alist_all_nodes()

        # Apply named filter if specified
        if filter_name:
            filter_obj = inventory_store.get_filter(filter_name)
            nodes = [node for node in nodes if filter_obj.matches(node)]
            log.info(
                f"Filtered to {len(nodes)} raw nodes using named filter '{filter_name}'"
            )
        else:
            # Get all query params as inline filter patterns
            filter_params = dict(request.query_params)

            # Apply inline filters if any field patterns provided
            if filter_params:
                filter_obj = InventoryFilter(filter_params)
                nodes = [node for node in nodes if filter_obj.matches(node)]
                log.info(
                    f"Filtered to {len(nodes)} raw nodes using inline filters: {filter_params}"
                )
            else:
                log.info(f"Exported {len(nodes)} raw nodes (no filter)")

        return nodes
    except Exception as e:
        log.error(f"Failed to export raw inventory: {e}")
        raise


@router.get("/inventory/fields")
async def get_inventory_fields(
    inventory_store: InventoryStore = Depends(get_inventory_store),
) -> dict[str, str]:
    """Get available filterable fields for the current inventory source."""
    return inventory_store.get_filterable_fields()


@router.get("/inventory/filters")
async def list_filters(
    inventory_store: InventoryStore = Depends(get_inventory_store),
) -> dict[str, str]:
    """List available named inventory filters for the current inventory source."""
    return inventory_store.get_available_filters()


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


@metrics_router.get("/metrics")
async def metrics(request: Request) -> Response:
    """Prometheus metrics endpoint (unauthenticated for Prometheus scraping).

    This endpoint is scraped by Prometheus to collect metrics.
    Metrics are collected fresh from Redis on each scrape (stateless).

    Note: This endpoint is intentionally unauthenticated to allow Prometheus
    to scrape metrics without authentication. Metrics contain only aggregated
    statistics with no sensitive details.
    """
    # Get Redis client from app state
    redis_client = request.app.state.redis_client

    # Create exporter and generate metrics
    exporter = MetricsExporter(redis_client)
    metrics_output = await exporter.generate_metrics()

    return Response(content=metrics_output, media_type="text/plain")


@router.get("/auth/debug")
async def debug_auth(auth: AuthResponse = Depends(do_auth)) -> dict:
    """Debug endpoint to see all authentication details including custom claims."""
    return {
        "method": auth["method"],
        "user": auth["user"],
        "provider": auth["provider"],
        "all_claims": auth.get(
            "claims", {}
        ),  # This will show ALL claims from the token
        "custom_claims": {
            k: v
            for k, v in auth.get("claims", {}).items()
            if k
            not in [
                "iss",
                "sub",
                "aud",
                "exp",
                "iat",
                "nbf",
                "jti",
                "at_hash",
                "nonce",
                "auth_time",
            ]
        },  # Filter to show only custom/non-standard claims
    }


@router.get("/userinfo")
async def get_userinfo(
    request: Request,
    access_token: str = Query(
        ..., description="OAuth access token to use for userinfo request"
    ),
    provider: Optional[str] = Query(
        None, description="Provider name (auto-detected from auth if not specified)"
    ),
    auth: AuthResponse = Depends(do_auth),
) -> dict:
    """Get user information from OIDC provider using the access token.

    This is a convenience/test endpoint. In production, clients should call
    the provider's userinfo endpoint directly.

    Note: Requires an access token, not an ID token. Access tokens are used
    for accessing resources, while ID tokens are used for authentication.
    """
    # Must be authenticated with JWT
    if auth["method"] != "jwt":
        raise TomAuthException("User info only available for JWT authentication")

    # Find the validator instance
    settings = request.app.state.settings
    validator = None

    # Use provider from query param, or fall back to authenticated provider
    target_provider = provider or auth["provider"]

    for v in request.app.state.jwt_providers:
        if v.name == target_provider:
            validator = v
            break

    if not validator:
        raise TomException(f"Provider {target_provider} not found")

    # Check if OAuth test endpoints are enabled globally
    if not settings.oauth_test_enabled:
        raise TomException(
            "OAuth test endpoints not enabled. Set oauth_test_enabled: true in config."
        )

    # Restrict to localhost when test endpoints are enabled
    _ensure_localhost(request)

    if not validator.oauth_test_userinfo_endpoint:
        raise TomException(
            f"Userinfo endpoint not available for provider {target_provider} - ensure discovery_url is configured"
        )

    # Call the OIDC userinfo endpoint with the access token
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                validator.oauth_test_userinfo_endpoint,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            response.raise_for_status()

            user_info = response.json()

            # Add provider info
            user_info["_provider"] = target_provider
            user_info["_auth_method"] = auth["method"]

            return user_info

        except httpx.HTTPStatusError as e:
            logging.error(
                f"Failed to get user info: {e.response.status_code} - {e.response.text}"
            )
            raise TomException(
                f"Failed to get user info from provider: {e.response.text}"
            )
        except Exception as e:
            logging.error(f"Error getting user info: {e}")
            raise TomException(f"Failed to get user info: {str(e)}")


# OAuth endpoints (not requiring authentication)
oauth_router = APIRouter()


def _ensure_localhost(request: Request):
    host = request.client.host if request.client else None
    if host not in {"127.0.0.1", "::1", "localhost"}:
        # Some proxies may set X-Forwarded-For; we intentionally keep this strict
        raise HTTPException(
            status_code=403, detail="OAuth test endpoints are restricted to localhost"
        )


class TokenRequest(BaseModel):
    """Request body for token exchange."""

    code: str
    state: str
    redirect_uri: str
    provider: Optional[str] = None
    code_verifier: Optional[str] = None


class TokenResponse(BaseModel):
    """Response for token exchange."""

    access_token: str
    token_type: str = "Bearer"
    expires_in: Optional[int] = None
    id_token: Optional[str] = None


@oauth_router.post("/oauth/token")
async def exchange_token(
    request: Request, token_request: TokenRequest
) -> TokenResponse:
    """Exchange OAuth authorization code for JWT token.

    This is a TEST/CONVENIENCE endpoint. In production, clients should handle
    OAuth flows themselves and only send validated JWTs to Tom.
    """
    settings = request.app.state.settings

    # Check if OAuth test endpoints are enabled globally
    if not settings.oauth_test_enabled:
        raise HTTPException(
            status_code=503,
            detail="OAuth test endpoints not enabled. Set oauth_test_enabled: true in config.",
        )

    # Restrict to localhost when test endpoints are enabled
    _ensure_localhost(request)

    # Find the validator for the requested provider (or first if not specified)
    validator = None
    provider_config = None

    for v in request.app.state.jwt_providers:
        # Find matching config
        for cfg in settings.jwt_providers:
            if cfg.enabled and cfg.name == v.name:
                if v.oauth_test_token_endpoint:
                    # Use this provider if it matches the request or no provider specified yet
                    if token_request.provider == v.name or (
                        not validator and not token_request.provider
                    ):
                        validator = v
                        provider_config = cfg
                        if token_request.provider:
                            break  # Exact match found
        if validator and token_request.provider:
            break  # Exact match found

    if not validator or not provider_config:
        raise HTTPException(
            status_code=503,
            detail=f"Provider '{token_request.provider}' not configured with valid discovery_url."
            if token_request.provider
            else "No provider configured with valid discovery_url.",
        )

    # Exchange the authorization code for tokens
    # Build token request data - support both PKCE and client_secret flows
    token_data = {
        "grant_type": "authorization_code",
        "code": token_request.code,
        "client_id": validator.client_id,
        "redirect_uri": token_request.redirect_uri,
    }

    # PKCE: include code_verifier if present
    if token_request.code_verifier:
        token_data["code_verifier"] = token_request.code_verifier

    # Traditional OAuth: include client_secret if present
    if provider_config.oauth_test_client_secret:
        token_data["client_secret"] = provider_config.oauth_test_client_secret

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                validator.oauth_test_token_endpoint,
                data=token_data,
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()

            token_data = response.json()

            # Log what tokens we received for debugging
            has_access = bool(token_data.get("access_token"))
            has_id = bool(token_data.get("id_token"))
            logging.info(
                f"Token exchange successful for {token_request.provider}: access_token={has_access}, id_token={has_id}"
            )

            # Return the token(s) exactly as provided by the OAuth provider
            return TokenResponse(
                access_token=token_data.get("access_token", ""),
                token_type=token_data.get("token_type", "Bearer"),
                expires_in=token_data.get("expires_in"),
                id_token=token_data.get("id_token"),
            )

        except httpx.HTTPStatusError as e:
            logging.error(
                f"Token exchange failed: {e.response.status_code} - {e.response.text}"
            )
            raise HTTPException(
                status_code=e.response.status_code,
                detail=f"Token exchange failed: {e.response.text}",
            )
        except Exception as e:
            logging.error(f"Token exchange error: {e}")
            raise HTTPException(
                status_code=500, detail=f"Token exchange failed: {str(e)}"
            )


@oauth_router.get("/oauth/config")
async def get_oauth_config(request: Request) -> dict:
    """Get OAuth configuration for the test frontend.

    This is a TEST/CONVENIENCE endpoint that returns config for oauth-test.html.
    Returns all enabled providers with OAuth test endpoints.
    """
    settings = request.app.state.settings

    # Check if OAuth test endpoints are enabled globally
    if not settings.oauth_test_enabled:
        return {
            "error": "OAuth test endpoints not enabled. Set oauth_test_enabled: true in config."
        }

    # Restrict to localhost when test endpoints are enabled
    _ensure_localhost(request)

    # Build redirect URI from actual request
    redirect_uri = f"{request.url.scheme}://{request.url.netloc}/static/oauth-test.html"

    # Collect all enabled providers with test authorization endpoints
    providers = []
    for validator in request.app.state.jwt_providers:
        if validator.oauth_test_authorization_endpoint:
            # Find matching config for scopes
            provider_scopes = ["openid", "email", "profile"]  # default
            for cfg in settings.jwt_providers:
                if cfg.enabled and cfg.name == validator.name:
                    provider_scopes = cfg.oauth_test_scopes
                    break

            providers.append(
                {
                    "name": validator.name,
                    "authorization_url": validator.oauth_test_authorization_endpoint,
                    "client_id": validator.client_id,
                    "scopes": " ".join(provider_scopes),
                }
            )

    if not providers:
        return {"error": "No provider with valid discovery_url configured."}

    return {
        "redirect_uri": redirect_uri,
        "providers": providers,
    }


if os.getenv("TOM_ENABLE_TEST_RECORDING", "").lower() == "true":
    logger.warning(
        "WARN:\t  TOM_ENABLE_TEST_RECORDING=true - this is a DEVELOPER ONLY feature"
    )

    @oauth_router.post("/dev/record-jwt")
    async def record_jwt_for_testing(request: Request):
        # Restrict to localhost regardless of oauth_test_enabled flag
        _ensure_localhost(request)
        """
        DEVELOPER ONLY: Record a JWT for test fixtures.
        
        Set TOM_ENABLE_TEST_RECORDING=true to enable this endpoint.
        Send a valid JWT via Authorization header, and this will:
        1. Validate it (or record validation failure)
        2. Extract all claims
        3. Save to tests/fixtures/jwt/{provider}_{validity}_{timestamp}.yaml
        
        This endpoint accepts both valid and invalid tokens.
        Disabled in production by default.
        """

        # Get raw token
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return {
                "error": "Missing or invalid Authorization header",
                "expected": "Authorization: Bearer <token>",
            }

        token = auth_header[7:]  # Remove "Bearer " prefix

        # Try to validate the token
        valid = False
        error = None
        provider = None
        user = None
        claims = None
        validator = None

        try:
            # Use the internal JWT auth function
            auth_result = await _jwt_auth(token, request.app.state.jwt_providers)
            valid = True
            provider = auth_result["provider"]
            user = auth_result["user"]
            claims = auth_result["claims"]

            # Find the validator that was used
            for v in request.app.state.jwt_providers:
                if v.name == provider:
                    validator = v
                    break
        except TomAuthException as e:
            error = str(e)
            # Try to extract provider from unverified token for filename
            try:
                unverified = jose_jwt.get_unverified_claims(token)
                issuer = unverified.get("iss", "unknown")
                # Try to match issuer to provider name
                for p in request.app.state.jwt_providers:
                    if p.issuer == issuer:
                        provider = p.name
                        validator = p
                        break
                if not provider:
                    provider = "unknown"
            except:
                provider = "unknown"

        # Create fixture structure
        fixture = {
            "description": f"Recorded from live {provider} token"
            if valid
            else f"Invalid token - {error}",
            "recorded_at": datetime.utcnow().isoformat() + "Z",
            "provider": provider,
            "jwt": token,
            "expected": {
                "valid": valid,
            },
        }

        # Add provider configuration used for validation
        if validator:
            fixture["provider_config"] = {
                "name": validator.name,
                "discovery_url": validator.discovery_url,
                "client_id": validator.client_id,
                "issuer": validator.issuer,
                "jwks_uri": validator.jwks_uri,
                "audience": validator.audience,
                "leeway_seconds": validator.leeway_seconds,
            }
            # Add tenant_id for Entra
            if hasattr(validator, "tenant_id") and validator.tenant_id:
                fixture["provider_config"]["tenant_id"] = validator.tenant_id

        # Add error if invalid
        if not valid:
            fixture["expected"]["error"] = error

        # Add claims and user info if valid
        if valid and claims is not None:
            fixture["expected"]["user"] = user
            fixture["expected"]["provider"] = provider
            fixture["expected"]["claims"] = claims

            # Add time information for expiration testing
            iat = claims.get("iat")
            if iat:
                fixture["validation_time"] = (
                    datetime.utcfromtimestamp(iat).isoformat() + "Z"
                )
            exp = claims.get("exp")
            if exp:
                fixture["expiration_time"] = (
                    datetime.utcfromtimestamp(exp).isoformat() + "Z"
                )

        # Create fixtures directory
        project_root = Path(request.app.state.settings.project_root)
        fixtures_dir = project_root / "tests" / "fixtures" / "jwt"
        fixtures_dir.mkdir(parents=True, exist_ok=True)

        # Create filename
        timestamp = int(datetime.utcnow().timestamp())
        validity = "valid" if valid else "invalid"
        filename = f"{provider}_{validity}_{timestamp}.yaml"
        filepath = fixtures_dir / filename

        # Save fixture
        with open(filepath, "w") as f:
            yaml.dump(fixture, f, default_flow_style=False, sort_keys=False)

        return {
            "message": "JWT fixture recorded",
            "file": str(filepath.relative_to(project_root)),
            "valid": valid,
            "provider": provider,
            "user": user if valid else None,
        }


@router.get("/templates/textfsm")
async def list_textfsm_templates(request: Request):
    """List all available TextFSM templates."""

    settings = request.app.state.settings
    template_dir = Path(settings.textfsm_template_dir)
    parser = TextFSMParser(custom_template_dir=template_dir)
    return parser.list_templates()


@router.post("/parse/test")
async def test_parse(
    request: Request,
    raw_output: str,
    parser: str = Query("textfsm", description="Parser to use ('textfsm' or 'ttp')"),
    template: Optional[str] = Query(
        None, description="Template name (e.g., 'my_template.textfsm')"
    ),
    device_type: Optional[str] = Query(
        None, description="Device type for auto-discovery (e.g., 'cisco_ios')"
    ),
    command: Optional[str] = Query(
        None, description="Command for auto-discovery (e.g., 'show ip int brief')"
    ),
    include_raw: bool = Query(False, description="Include raw output in response"),
):
    """Test parsing endpoint - parse raw text with a specified template.

    This is a convenience endpoint for testing templates without executing commands.
    """

    if parser not in ["textfsm", "ttp"]:
        raise TomValidationException(
            f"Parser '{parser}' not supported. Use 'textfsm' or 'ttp'"
        )

    settings = request.app.state.settings

    return parse_output(
        raw_output=raw_output,
        settings=settings,
        device_type=device_type,
        command=command,
        template=template,
        include_raw=include_raw,
        parser_type=parser,
    )
