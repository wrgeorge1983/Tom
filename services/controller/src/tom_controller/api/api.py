import logging
from typing import Optional

from fastapi import APIRouter, Depends, Request, Query, HTTPException, Response
import httpx
import saq

from tom_controller.api.auth import AuthResponse, do_auth
from tom_controller.api.models import JobResponse
from tom_controller.monitoring import MetricsExporter
from tom_controller.exceptions import TomException, TomAuthException
from tom_controller.parsing import parse_output

logger = logging.getLogger(__name__)


class AuthRouter(APIRouter):
    auth_dep = Depends(do_auth)

    def __init__(self, *args, **kwargs):
        default_dependencies = kwargs.get("dependencies", [])
        kwargs["dependencies"] = [self.auth_dep] + default_dependencies
        super().__init__(*args, **kwargs)


api_router = AuthRouter()

# Unauthenticated router for Prometheus metrics
prometheus_router = APIRouter()


def _ensure_localhost(request: Request):
    """Restrict endpoint to localhost only."""
    host = request.client.host if request.client else None
    if host not in {"127.0.0.1", "::1", "localhost"}:
        raise HTTPException(
            status_code=403, detail="OAuth test endpoints are restricted to localhost"
        )


@api_router.get("/")
async def root():
    return {"message": "Hello World"}


@api_router.get("/job/{job_id}")
async def job(
    request: Request,
    job_id: str,
    parse: bool = Query(False, description="Parse output using TextFSM"),
    parser: str = Query("textfsm", description="Parser to use"),
    template: Optional[str] = Query(None, description="Template name for parsing"),
    include_raw: bool = Query(False, description="Include raw output with parsed"),
) -> Optional[JobResponse]:
    """Get job status and results by job ID.

    Returns a consistent JobResponse envelope containing:
    - job_id: Unique identifier for the job
    - status: Job status (QUEUED, COMPLETE, FAILED, etc.)
    - result: When complete, contains {"data": {...}, "meta": {...}}
    - attempts: Number of execution attempts
    - error: Error message if failed

    When parse=true and the job is complete, the command output in result.data
    will be the parsed structured data instead of raw text.

    Returns None if the job is not found.
    """
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

        # Extract device_type from metadata
        device_type = None
        if job_response.metadata:
            device_type = job_response.metadata.get("device_type")

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

        return job_response.with_parsed_result(parsed_results)

    return job_response


@prometheus_router.get("/metrics")
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


@api_router.get("/auth/debug")
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


@api_router.get("/userinfo")
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


# Include sub-routers
from tom_controller.api import (
    raw,
    device,
    inventory,
    templates,
    oauth_test,
    credentials,
    cache_api,
)

api_router.include_router(raw.router)
api_router.include_router(device.router)
api_router.include_router(inventory.router)
api_router.include_router(templates.router)
api_router.include_router(credentials.router)
api_router.include_router(cache_api.router)

# OAuth test router is separate (unauthenticated)
oauth_test_router = oauth_test.router
