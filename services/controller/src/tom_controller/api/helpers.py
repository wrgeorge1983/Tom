import asyncio
import logging

import saq
from pydantic import BaseModel
from saq.job import Job, TERMINAL_STATUSES
from saq import Status

from tom_controller.api.models import JobResponse
from tom_controller.exceptions import TomJobEnqueueError

logger = logging.getLogger(__name__)

# Polling intervals for the early-completion guard. These cover the window
# where a very fast job (e.g. cache hit) might complete before the pubsub
# listener is subscribed, causing the notification to be lost. After these
# polls, we rely solely on pubsub for the remainder of the timeout.
_GUARD_POLL_DELAYS = [0.05, 0.10, 0.15, 0.25]


async def _wait_for_job(job: Job, timeout: float) -> None:
    """Wait for a job to reach a terminal status.

    Runs two concurrent strategies and returns as soon as either succeeds:

      1. Pubsub listener  -- SAQ's built-in ``job.refresh(until_complete=...)``
         which subscribes to Redis pubsub for instant notification.

      2. Polling guard -- a few quick Redis GETs in the first ~500ms to catch
         completions that arrived before the pubsub subscription was active.

    This works around a race condition in SAQ where the worker's PUBLISH can
    arrive before the controller has subscribed. See SAQ issue #118.
    """
    completed = asyncio.Event()

    async def _pubsub_wait() -> None:
        """Listen via pubsub for the job to complete."""
        try:
            await job.refresh(until_complete=timeout)
        except TimeoutError:
            return
        if job.status in TERMINAL_STATUSES:
            completed.set()

    async def _poll_guard() -> None:
        """Poll Redis a few times in the early window to catch fast completions."""
        for delay in _GUARD_POLL_DELAYS:
            await asyncio.sleep(delay)
            if completed.is_set():
                return
            refreshed = await job.get_queue().job(job.key)
            if refreshed and refreshed.completed:
                job.replace(refreshed)
                completed.set()
                return

    pubsub_task = asyncio.create_task(_pubsub_wait())
    poll_task = asyncio.create_task(_poll_guard())

    try:
        await asyncio.wait_for(completed.wait(), timeout=timeout)
    except TimeoutError:
        # Neither strategy found completion. One final check.
        await job.refresh()
        if job.status in TERMINAL_STATUSES:
            return
        raise TimeoutError(f"Job {job.id} did not complete within {timeout}s")
    finally:
        pubsub_task.cancel()
        poll_task.cancel()
        for task in [pubsub_task, poll_task]:
            try:
                await task
            except (asyncio.CancelledError, TimeoutError):
                pass


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
            await _wait_for_job(job, float(timeout))
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
