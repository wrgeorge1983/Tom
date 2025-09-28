import logging
from typing import Optional, TypedDict, Literal, Dict, Any

from fastapi import APIRouter, Depends, Request, Query, HTTPException
from pydantic import BaseModel
import saq
import httpx

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
from tom_controller.auth import get_jwt_validator, JWTValidationError


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


async def jwt_auth(request: Request) -> AuthResponse:
    """Validate JWT from Authorization header."""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise TomAuthException("Missing or invalid Bearer token")

    token = auth_header[7:]  # Remove "Bearer " prefix

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

    # Try each enabled provider
    for provider_config in settings.jwt_providers:
        if not provider_config.enabled:
            continue

        try:
            # Convert Pydantic model to dict for validator
            config_dict = provider_config.model_dump()
            validator = get_jwt_validator(config_dict)

            claims = await validator.validate_token(token)
            user = validator.get_user_identifier(claims)

            # Clean up validator resources
            await validator.close()

            return {
                "method": "jwt",
                "user": user,
                "provider": provider_config.name,
                "claims": claims,
            }

        except JWTValidationError as e:
            logging.debug(
                f"JWT validation failed for provider {provider_config.name}: {e}"
            )
            continue  # Try next provider

        except Exception as e:
            logging.error(
                f"Unexpected error validating JWT with {provider_config.name}: {e}"
            )
            continue

    raise TomAuthException("Invalid JWT token - no provider could validate it")


async def do_auth(request: Request) -> AuthResponse:
    settings = request.app.state.settings

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
            raise TomException(f"Failed to enqueue job for {device_name}: {e}") from e

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
            raise TomException(f"Failed to enqueue job for {device_name}: {e}") from e

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
            raise TomException(f"Failed to enqueue job for {device_name}: {e}") from e

    elif device_config.adapter == "scrapli":
        args = ScrapliSendCommandModel(**kwargs)
        try:
            response = await enqueue_job(
                queue, "send_commands_scrapli", args, wait=wait
            )
        except Exception as e:
            raise TomException(f"Failed to enqueue job for {device_name}: {e}") from e

    else:
        raise TomException(f"Unknown device type {type(device_config)}")

    return response


# OAuth endpoints (not requiring authentication)
oauth_router = APIRouter()


class TokenRequest(BaseModel):
    """Request body for token exchange."""

    code: str
    state: str
    redirect_uri: str = "http://localhost:8000/static/oauth-test.html"


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

    This endpoint handles the token exchange for the OAuth flow.
    It's not protected by authentication since it's part of the auth flow itself.
    """
    settings = request.app.state.settings

    # Find the first enabled OAuth provider with token exchange capability
    provider_config = None
    for provider in settings.jwt_providers:
        if provider.enabled and provider.client_secret and provider.token_url:
            provider_config = provider
            break

    if not provider_config:
        raise HTTPException(
            status_code=500,
            detail="No OAuth provider configured with token exchange capability",
        )

    # Exchange the authorization code for tokens
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                provider_config.token_url,
                data={
                    "grant_type": "authorization_code",
                    "code": token_request.code,
                    "client_id": provider_config.client_id,
                    "client_secret": provider_config.client_secret,
                    "redirect_uri": token_request.redirect_uri,
                },
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()

            token_data = response.json()

            # Return the token(s)
            return TokenResponse(
                access_token=token_data.get("access_token")
                or token_data.get("id_token"),
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
    """Get OAuth configuration for the frontend.

    Returns the OAuth URLs needed by the frontend to initiate the flow.
    """
    settings = request.app.state.settings

    # Find the first enabled OAuth provider
    for provider in settings.jwt_providers:
        if provider.enabled and provider.authorization_url:
            return {
                "provider": provider.name,
                "authorization_url": provider.authorization_url,
                "client_id": provider.client_id,
                "redirect_uri": "http://localhost:8000/static/oauth-test.html",
            }

    return {"error": "No OAuth provider configured"}
