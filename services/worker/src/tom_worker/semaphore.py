import logging
from contextlib import asynccontextmanager
from typing import Optional

import redis.asyncio as redis
import saq.types

from tom_worker.exceptions import AuthenticationException, PermanentException
from tom_worker.retry_handler import RetryHandler

logger = logging.getLogger(__name__)


class DeviceSemaphore:
    def __init__(
        self, redis_client: redis.Redis, device_id: str, max_concurrent_tasks: int = 1
    ):
        self.redis_client = redis_client
        self.device_id = device_id
        self.max_concurrent_tasks = max_concurrent_tasks
        self.lease_key = f"device_lease:{device_id}"
        self.lease_ttl = 120  # 2 minute lease timeout if not cancelled earlier

    async def acquire_lease(self, job_id: str) -> bool:
        """Try to acquire a lease for this device.  True if successful"""

        lua_script = """
        local lease_key = KEYS[1]
        local job_id = ARGV[1]
        local max_concurrent = tonumber(ARGV[2])
        local lease_ttl = tonumber(ARGV[3])
        local current_time = redis.call('TIME')[1]
        
        -- Clean up expired leases first
        redis.call('ZREMRANGEBYSCORE', lease_key, 0, current_time)
        
        -- Check current lease count 
        local current_count = redis.call('ZCARD', lease_key)
        if current_count >= max_concurrent then
            return 0 -- Reject: no more leases available
        end 
        
        -- Acquire a lease
        local expire_time = current_time + lease_ttl
        redis.call('ZADD', lease_key, expire_time, job_id)
        redis.call('EXPIRE', lease_key, lease_ttl * 2) -- Expire lease if not used within 2x lease_ttl
        return 1 
        
        """
        result = await self.redis_client.eval(
            lua_script,
            1,
            self.lease_key,
            job_id,
            str(self.max_concurrent_tasks),
            str(self.lease_ttl),
        )
        return bool(result)

    async def release_lease(self, job_id: str):
        """Release a lease for this device"""
        await self.redis_client.zrem(self.lease_key, job_id)


@asynccontextmanager
async def device_lease(
    ctx: saq.types.Context,
    redis_client: redis.Redis,
    device_id: str,
    job_id: str,
    max_queue_wait: Optional[int] = None,
):
    """
    Async context manager for acquiring a device semaphore with retry handling.

    Handles:
    - Semaphore acquisition with time-based retry budget
    - Restoration of normal retry settings after lease acquired
    - Marking non-retryable errors (auth failures, permanent errors)
    - Automatic lease release on exit

    Usage:
        async with device_lease(ctx, redis_client, device_id, job_id, max_queue_wait):
            async with await SomeAdapter.from_model(model, creds) as adapter:
                result = await adapter.send_commands(commands)
    """
    semaphore = DeviceSemaphore(redis_client=redis_client, device_id=device_id)
    lease_acquired = await semaphore.acquire_lease(job_id)

    # Handle device busy with time-based retry budget
    # This may raise GatingException to trigger SAQ retry
    RetryHandler.handle_device_busy(ctx, device_id, lease_acquired, max_queue_wait)

    try:
        # Restore original retry settings now that we have the lease
        # This ensures other errors (network, auth) get normal retry behavior
        RetryHandler.restore_original_settings(ctx)
        yield semaphore
    except (AuthenticationException, PermanentException) as e:
        # Mark job as non-retryable by setting retries = attempts
        # This prevents SAQ from retrying authentication failures
        job = ctx.get("job")
        if job:
            job.retries = job.attempts
        logger.error(f"Non-retryable error for {device_id}: {e}")
        raise
    finally:
        await semaphore.release_lease(job_id)
