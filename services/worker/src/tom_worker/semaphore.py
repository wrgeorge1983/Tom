import asyncio
import redis.asyncio as redis

class DeviceSemaphore:
    def __init__(self, redis_client: redis.Redis, device_id: str, max_concurrent_tasks: int = 1):
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
            lua_script, 1, self.lease_key, job_id,
            str(self.max_concurrent_tasks), str(self.lease_ttl)
        )
        return bool(result)

    async def release_lease(self, job_id: str):
        """Release a lease for this device"""
        await self.redis_client.zrem(self.lease_key, job_id)
