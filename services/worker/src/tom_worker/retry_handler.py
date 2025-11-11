"""Retry handling utilities for different exception types."""

import logging
from typing import Any, Dict

from tom_worker.exceptions import GatingException, PermanentException

logger = logging.getLogger(__name__)


class RetryHandler:
    """Manages retry behavior for different exception types."""
    
    # Default retry intervals for different scenarios (in seconds)
    GATING_RETRY_INTERVAL = 2.0  # Check every 2s for busy devices
    TRANSIENT_RETRY_INTERVAL = 1.0  # Default for transient errors
    
    @staticmethod
    def configure_for_gating(ctx: Dict[str, Any]) -> None:
        """Configure retry behavior for device gating (busy) scenarios.
        
        Modifies the job's retry parameters to use fixed intervals instead
        of exponential backoff, which is more appropriate for waiting on
        busy resources.
        
        Args:
            ctx: SAQ job context containing the job
        """
        job = ctx.get("job")
        if not job:
            logger.error("No job found in context")
            return
        
        # Only configure once per job
        if "gating_retry_configured" in ctx:
            return
            
        # Store original retry settings if not already stored
        if "original_retry_settings" not in ctx:
            ctx["original_retry_settings"] = {
                "retries": job.retries,
                "retry_delay": job.retry_delay,
                "retry_backoff": job.retry_backoff,
            }
            
        # Calculate how many retries we can do within original tolerance
        # Original tolerance = retries * retry_delay (with backoff, it's more complex)
        original_settings = ctx["original_retry_settings"]
        
        if original_settings["retry_backoff"]:
            # With exponential backoff, calculate approximate max wait time
            # Sum of geometric series: delay * (2^n - 1) where n is number of retries
            max_wait_time = original_settings["retry_delay"] * (2**original_settings["retries"] - 1)
        else:
            # Without backoff, it's simple multiplication
            max_wait_time = original_settings["retry_delay"] * original_settings["retries"]
            
        # Calculate how many fixed-interval retries we can fit
        max_gating_retries = int(max_wait_time / RetryHandler.GATING_RETRY_INTERVAL)
        
        # Configure job for fixed-interval retries
        job.retries = max(max_gating_retries, job.attempts + 1)  # At least one more try
        job.retry_delay = RetryHandler.GATING_RETRY_INTERVAL
        job.retry_backoff = False
        
        ctx["gating_retry_configured"] = True
        ctx["max_gating_retries"] = max_gating_retries
        
        logger.info(
            f"Configured job {job.id} for gating retries: "
            f"{max_gating_retries} attempts at {RetryHandler.GATING_RETRY_INTERVAL}s intervals "
            f"(based on original tolerance of ~{max_wait_time:.1f}s)"
        )
    
    @staticmethod
    def handle_device_busy(
        ctx: Dict[str, Any],
        device_id: str,
        semaphore_acquired: bool
    ) -> None:
        """Handle device busy scenario with appropriate retry configuration.
        
        Args:
            ctx: SAQ job context
            device_id: Device identifier
            semaphore_acquired: Whether the semaphore was acquired
            
        Raises:
            GatingException: If device is busy but retries remain
            PermanentException: If retry tolerance exceeded
        """
        if semaphore_acquired:
            return
            
        # Configure retry behavior for gating
        RetryHandler.configure_for_gating(ctx)
        
        job = ctx["job"]
        max_retries = ctx.get("max_gating_retries", job.retries)
        
        # Check if we've exceeded our retry tolerance
        if job.attempts >= max_retries:
            elapsed_time = job.attempts * RetryHandler.GATING_RETRY_INTERVAL
            logger.error(
                f"Device {device_id} busy timeout after {job.attempts} attempts "
                f"(~{elapsed_time:.1f}s elapsed)"
            )
            raise PermanentException(
                f"Device {device_id} remained busy after {job.attempts} attempts "
                f"over ~{elapsed_time:.1f} seconds"
            )
        
        # Log progress periodically
        if job.attempts == 0:
            logger.info(f"Device {device_id} is busy, will retry with fixed intervals")
        elif job.attempts % 10 == 0:
            elapsed_time = job.attempts * RetryHandler.GATING_RETRY_INTERVAL
            logger.info(
                f"Device {device_id} still busy after {job.attempts} attempts "
                f"(~{elapsed_time:.1f}s elapsed)"
            )
        else:
            logger.debug(
                f"Device {device_id} busy, attempt {job.attempts + 1}/{max_retries}"
            )
        
        raise GatingException(f"{device_id} busy. Lease not acquired.")
    
    @staticmethod
    def restore_original_settings(ctx: Dict[str, Any]) -> None:
        """Restore original retry settings if they were modified.
        
        This can be called after successfully acquiring a resource
        to restore normal retry behavior for subsequent errors.
        
        Args:
            ctx: SAQ job context
        """
        if "original_retry_settings" not in ctx:
            return
            
        job = ctx["job"]
        original = ctx["original_retry_settings"]
        
        job.retries = original["retries"]
        job.retry_delay = original["retry_delay"]
        job.retry_backoff = original["retry_backoff"]
        
        # Clean up context flags
        ctx.pop("gating_retry_configured", None)
        ctx.pop("max_gating_retries", None)
        
        logger.debug(f"Restored original retry settings for job {job.id}")