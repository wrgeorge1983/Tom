import json
import logging
import datetime
from typing import Any, Optional, TypedDict, Literal

import redis.asyncio as aioredis

from tom_controller.config import Settings
from tom_controller.exceptions import TomCacheSerializationError

logger = logging.getLogger(__name__)

CacheStatus = Literal["hit", "miss", "disabled", "error"]

class CacheResult(TypedDict, total=False):
    status: CacheStatus
    value: Optional[Any]
    ttl: Optional[int]
    cached_at: Optional[str]
    age_seconds: Optional[float]

def bad_cache_result(status: CacheStatus) -> CacheResult:
    return CacheResult(
        status=status,
        value=None,
        ttl=None,
        cached_at=None,
        age_seconds=None
    )

class CacheManager:
    """Manages Redis-backed caching for device command results."""
    def __init__(self, redis_client: aioredis.Redis, settings: Settings):
        self.redis_client = redis_client
        self.settings = settings

    async def get(self, key: str) -> CacheResult:
        """Get cached result

        Returns:
            Cached entry dict or None if not found/disable
        """
        if not self.settings.cache_enabled:
            return bad_cache_result("disabled")

        key = self._make_full_key(key)

        try:
            raw_result = await self.redis_client.get(key)
        except Exception as e:
            logger.error(f"Failed to get cache entry {key}: {e}")
            return bad_cache_result("error")

        if raw_result is None:
            logger.debug(f"Cache miss for key {key}")
            return bad_cache_result("miss")

        try:
            result = json.loads(raw_result)
            return {
                "status": "hit",
                "value": result["result"],
                "ttl": result["ttl"],
                "cached_at": result["cached_at"],
                "age_seconds": self._calculate_age(result["cached_at"]),
            }

        except json.JSONDecodeError:
            logger.warning(f"Failed to decode cache entry {key}: {raw_result}")
            return bad_cache_result("error")

    async def set(self, key: str, value: Any, ttl: Optional[int] = None):
        """Store result in cache

        Returns:

            """

        if not self.settings.cache_enabled:
            return

        key = self._make_full_key(key)

        ttl = min(ttl or self.settings.cache_default_ttl, self.settings.cache_max_ttl)

        if ttl < 0:
            raise ValueError("TTL must be non-negative")

        cache_entry = {
            "result": value,
            "ttl": ttl,
            "cached_at": datetime.datetime.now(datetime.UTC).isoformat(),
        }

        try:
            entry = json.dumps(cache_entry)
        except TypeError as e:
            logger.warning(f"Failed to encode cache entry {key}: {value}")
            raise TomCacheSerializationError(f"Failed to encode cache entry: {e}") from e

        try:
            await self.redis_client.setex(key, ttl, entry)

        except Exception as e:
            logger.error(f"Failed to set cache entry {key}: {e}")
            return

        logger.debug(f"Cache set for key {key} (ttl={ttl})")
        return

    async def delete(self, key: str):
        """Delete cache entry"""
        if not self.settings.cache_enabled:
            return
        key = self._make_full_key(key)

        try:
            await self.redis_client.delete(key)
            logger.debug(f"Cache deleted for key {key}")
        except Exception as e:
            logger.error(f"Failed to delete cache entry {key}: {e}")


    async def invalidate_device(self, device_name: str) -> int:
        """Delete all cache entries for a device"""
        if not self.settings.cache_enabled:
            return 0
        pattern = f"{self.settings.cache_key_prefix}:{device_name}:*"
        keys = await self.redis_client.keys(pattern)

        if keys:
            try:
                deleted = await self.redis_client.delete(*keys)
                logger.debug(f"Invalidated {deleted} cache entries for device {device_name}")
                return deleted
            except Exception as e:
                logger.error(f"Failed to invalidate cache entries for device {device_name}: {e}")

        return 0

    async def clear_all(self) -> int:
        """Clear all cache entries"""
        if not self.settings.cache_enabled:
            return 0
        keys = await self.redis_client.keys(f"{self.settings.cache_key_prefix}:*")
        if keys:
            try:
                deleted = await self.redis_client.delete(*keys)
                logger.debug(f"Cleared {deleted} cache entries")
                return deleted
            except Exception as e:
                logger.error(f"Failed to clear cache entries: {e}")

        return 0

    async def list_keys(self, device_name: Optional[str] = None) -> list[str]:
        """List all cache keys, optionally filtered by device name"""
        if not self.settings.cache_enabled:
            return []

        if device_name:
            pattern = f"{self.settings.cache_key_prefix}:{device_name}:*"

        else:
            pattern = f"{self.settings.cache_key_prefix}:*"

        try:
            keys = await self.redis_client.keys(pattern)
            prefix_len = len(self.settings.cache_key_prefix) + 1
            return [key[prefix_len:] for key in keys]
        except Exception as e:
            logger.error(f"Failed to list cache keys: {e}")
            return []

    @staticmethod
    def _calculate_age(cached_at: Optional[str]) -> Optional[float]:
        if not cached_at:
            return None
        try:
            cached_at_dt = datetime.datetime.fromisoformat(cached_at)
        except (ValueError, TypeError):
            logger.warning(
                f"Failed to parse cached_at value '{cached_at}' as ISO 8601 datetime"
            )
            return None

        age = datetime.datetime.now(datetime.UTC) - cached_at_dt
        return age.total_seconds()

    def _make_full_key(self, key: str) -> str:
        if not isinstance(key, str):
            raise TypeError("Key must be a string")

        if not key:
            raise ValueError("Key must not be empty")

        if not key.startswith(self.settings.cache_key_prefix):
            key = f'{self.settings.cache_key_prefix}:{key}'

        return key

    def generate_cache_key(self, device_name: str, command_name: str) -> str:
        device_name = " ".join(device_name.split()).strip().lower()
        command_name = " ".join(command_name.split()).strip().lower()
        return f"{self.settings.cache_key_prefix}:{device_name}:{command_name}"