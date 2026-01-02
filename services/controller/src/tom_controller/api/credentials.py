"""API endpoints for credential management."""

import logging

import saq
from fastapi import APIRouter
from starlette.requests import Request

from tom_controller.exceptions import TomException

logger = logging.getLogger(__name__)

router = APIRouter(tags=["credentials"])


@router.get("/credentials")
async def list_credentials(
    request: Request,
    timeout: int = 30,
) -> dict:
    """List all available credential IDs from the configured credential store.

    This endpoint queries the worker's credential plugin to enumerate
    all available credentials. Only credential IDs are returned, not
    the actual credential values.

    :param timeout: Maximum time to wait for worker response (seconds)
    :return: Dictionary with list of credential IDs
    """
    queue: saq.Queue = request.app.state.queue

    logger.info("Listing credentials from worker")

    job = await queue.enqueue(
        "list_credentials",
        timeout=timeout,
    )

    await job.refresh(until_complete=float(timeout))

    if job.status == saq.Status.COMPLETE:
        logger.info(f"Credential list job {job.id} completed")
        return job.result
    elif job.status == saq.Status.FAILED:
        error_msg = job.error or "Unknown error"
        logger.error(f"Credential list job {job.id} failed: {error_msg}")
        raise TomException(f"Failed to list credentials: {error_msg}")
    else:
        logger.warning(f"Credential list job {job.id} timed out (status: {job.status})")
        raise TomException(f"Credential list request timed out after {timeout}s")
