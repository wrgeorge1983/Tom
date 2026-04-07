"""Retry handling utilities for different exception types."""

import logging
import time
from typing import Any, Dict

from tom_worker.exceptions import GatingException, PermanentException

logger = logging.getLogger(__name__)


class RetryHandler:
    """Manages retry behavior for different exception types."""

    # Default retry interval for gating (in seconds)
    GATING_RETRY_INTERVAL = 2.0  # Check every 2s for busy devices

    @staticmethod
    def handle_device_busy(
        ctx: Dict[str, Any],
        device_id: str,
        semaphore_acquired: bool,
        max_queue_wait: int,
    ) -> None:
        """Handle device busy scenario with time-based retry budget.

        Tracks cumulative time spent waiting for semaphore acquisition across
        all retry attempts. Fails permanently when max_queue_wait is exceeded.

        State that must survive across SAQ retries (ctx is ephemeral, rebuilt
        fresh on each dequeue) is stored in job.meta, which is persisted to
        Redis with the job.

        Args:
            ctx: SAQ job context
            device_id: Device identifier
            semaphore_acquired: Whether the semaphore was acquired
            max_queue_wait: Maximum total seconds to wait for semaphore across all attempts

        Raises:
            GatingException: If device semaphore not acquired but time budget remains
            PermanentException: If time budget exceeded
        """
        if semaphore_acquired:
            return

        job = ctx["job"]
        job_id = job.id

        GATING_START_KEY = "gating_start_time"
        GATING_COUNT_KEY = "gating_attempt_count"
        ORIGINAL_SETTINGS_KEY = "original_retry_settings"

        # Initialize cumulative wait tracking on first gating attempt.
        # job.meta persists across retries; ctx does not.
        if GATING_START_KEY not in job.meta:
            job.meta[GATING_START_KEY] = time.time()
            job.meta[GATING_COUNT_KEY] = 0

            # Store original retry settings to restore after semaphore acquisition
            job.meta[ORIGINAL_SETTINGS_KEY] = {
                "retries": job.retries,
                "retry_delay": job.retry_delay,
                "retry_backoff": job.retry_backoff,
            }

            # Configure job for fixed-interval gating retries.
            # We bail based on elapsed time, not attempt count.
            job.retries = 999999  # Effectively unlimited
            job.retry_delay = RetryHandler.GATING_RETRY_INTERVAL
            job.retry_backoff = False

            logger.info(
                f"Job {job_id}: Device {device_id} semaphore not available. "
                f"Will retry for up to {max_queue_wait}s"
            )

        # Calculate elapsed time since first gating attempt
        elapsed_time = time.time() - job.meta[GATING_START_KEY]
        job.meta[GATING_COUNT_KEY] += 1
        gating_count = job.meta[GATING_COUNT_KEY]

        # Check if we've exceeded our time budget
        if elapsed_time >= max_queue_wait:
            logger.error(
                f"Job {job_id}: Device {device_id} semaphore acquisition timeout after "
                f"{gating_count} attempts over {elapsed_time:.1f}s "
                f"(max_queue_wait={max_queue_wait}s)"
            )
            # Clean up job.meta for this job
            job.meta.pop(GATING_START_KEY, None)
            job.meta.pop(GATING_COUNT_KEY, None)
            job.meta.pop(ORIGINAL_SETTINGS_KEY, None)

            raise PermanentException(
                f"Unable to acquire semaphore for {device_id} after "
                f"{elapsed_time:.1f}s (max_queue_wait={max_queue_wait}s)"
            )

        # Log progress periodically
        if gating_count == 1:
            logger.info(
                f"Job {job_id}: Device {device_id} semaphore not available, "
                f"will retry every {RetryHandler.GATING_RETRY_INTERVAL}s"
            )
        elif gating_count % 10 == 0:
            remaining_time = max_queue_wait - elapsed_time
            logger.info(
                f"Job {job_id}: Device {device_id} still waiting for semaphore after "
                f"{gating_count} attempts ({elapsed_time:.1f}s elapsed, "
                f"{remaining_time:.1f}s remaining)"
            )
        else:
            logger.debug(
                f"Job {job_id}: Device {device_id} semaphore busy, "
                f"attempt {gating_count} ({elapsed_time:.1f}s elapsed)"
            )

        raise GatingException(f"Semaphore not available for {device_id}")

    @staticmethod
    def restore_original_settings(ctx: Dict[str, Any]) -> None:
        """Restore original retry settings after acquiring semaphore.

        This ensures that transient failures (network errors, etc.) after
        semaphore acquisition use the user's configured retry settings,
        not the gating retry settings.

        Args:
            ctx: SAQ job context
        """
        job = ctx["job"]
        job_id = job.id

        GATING_START_KEY = "gating_start_time"
        GATING_COUNT_KEY = "gating_attempt_count"
        ORIGINAL_SETTINGS_KEY = "original_retry_settings"

        if ORIGINAL_SETTINGS_KEY not in job.meta:
            return

        original = job.meta[ORIGINAL_SETTINGS_KEY]

        job.retries = original["retries"]
        job.retry_delay = original["retry_delay"]
        job.retry_backoff = original["retry_backoff"]

        # Log gating statistics
        if GATING_START_KEY in job.meta:
            total_gating_time = time.time() - job.meta[GATING_START_KEY]
            attempt_count = job.meta.get(GATING_COUNT_KEY, 0)
            logger.info(
                f"Job {job_id}: Semaphore acquired after {attempt_count} attempts "
                f"({total_gating_time:.1f}s). Restored retry settings: "
                f"retries={job.retries}, delay={job.retry_delay}s, backoff={job.retry_backoff}"
            )

        # Clean up gating state from job.meta
        job.meta.pop(GATING_START_KEY, None)
        job.meta.pop(GATING_COUNT_KEY, None)
        job.meta.pop(ORIGINAL_SETTINGS_KEY, None)

        logger.debug(f"Restored original retry settings for job {job_id}")
