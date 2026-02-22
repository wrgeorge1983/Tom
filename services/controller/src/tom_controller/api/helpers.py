import logging

import saq
from pydantic import BaseModel
from saq import Status

from tom_controller.api.models import JobResponse
from tom_controller.exceptions import TomJobEnqueueError

logger = logging.getLogger(__name__)


async def enqueue_job(
    queue: saq.Queue,
    function_name: str,
    args: BaseModel,
    wait: bool = False,
    timeout: int = 10,
    retries: int = 3,
    max_queue_wait: int = 300,
    job_label: str = "",
) -> JobResponse:
    label = f" for {job_label}" if job_label else ""

    logger.info(f"Enqueuing job{label}: {function_name}")

    try:
        job = await queue.enqueue(
            function_name,
            timeout=timeout,
            json=args.model_dump_json(),
            retries=retries,
            retry_delay=1.0,
            retry_backoff=True,
        )
    except Exception as e:
        logger.error(f"Failed to submit job to queue{label}: {e}")
        raise TomJobEnqueueError(f"Failed to submit job to queue{label}: {e}") from e

    logger.info(f"Enqueued job {job.id}{label} with retries={job.retries}")

    if wait:
        try:
            await job.refresh(until_complete=float(timeout))
        except TimeoutError:
            logger.warning(
                f"Job {job.id}{label} was enqueued but timed out after "
                f"{timeout}s waiting for result"
            )
            # Fall through -- return the job in whatever state it's in.
            # The caller sees a non-complete status and knows it's not done.
            job_response = JobResponse.from_job(job)
            return job_response

        if job.status == Status.COMPLETE:
            logger.info(
                f"Job {job.id}{label} completed successfully "
                f"after {job.attempts} attempt(s)"
            )
        elif job.status == Status.FAILED:
            error_summary = None
            if job.error:
                if "AuthenticationException" in job.error:
                    error_summary = "Authentication failed"
                elif "GatingException" in job.error:
                    error_summary = "Device busy"
                else:
                    error_lines = job.error.strip().split("\n")
                    if error_lines:
                        error_summary = error_lines[-1][:200]
            logger.error(
                f"Job {job.id}{label} FAILED after {job.attempts} "
                f"attempt(s) - {error_summary or 'Unknown error'}"
            )
        elif job.status == Status.ABORTED:
            logger.warning(
                f"Job {job.id}{label} was aborted after {job.attempts} attempt(s)"
            )
        else:
            logger.info(
                f"Job {job.id}{label} status: {job.status} "
                f"after {job.attempts} attempt(s)"
            )

    job_response = JobResponse.from_job(job)
    return job_response
