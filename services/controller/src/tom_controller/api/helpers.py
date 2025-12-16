import logging

import saq
from pydantic import BaseModel
from saq import Status

from tom_controller.api.models import JobResponse

logger = logging.getLogger(__name__)


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
