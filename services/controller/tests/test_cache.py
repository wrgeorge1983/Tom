import pytest
import pytest_asyncio
from fakeredis import aioredis as fake_aioredis
from freezegun import freeze_time

from tom_controller.cache.cache import CacheManager
from tom_controller.config import Settings


@pytest_asyncio.fixture
async def fake_redis():
    """In-memory fake Redis with real behavior."""
    client = fake_aioredis.FakeRedis(decode_responses=True)
    yield client
    await client.flushall()
    await client.aclose()


@pytest_asyncio.fixture
def test_settings():
    """Cache settings for testing."""
    return Settings(
        cache_enabled=True,
        cache_default_ttl=300,
        cache_max_ttl=3600,
        cache_key_prefix="TEST_CACHE",
        # Required settings for Settings class
        redis_host="localhost",
        redis_port=6379,
        inventory_type="yaml",
    )


class TestCacheBasics:
    @pytest.mark.asyncio
    async def test_cache_disabled(self, fake_redis):
        """Cache returns disabled status when disabled."""
        # Create settings with cache disabled
        settings = Settings(
            redis_host="localhost",
            redis_port=6379,
            inventory_type="yaml",
        )
        # Manually override cache_enabled after creation since pydantic-settings
        # loads from env/yaml files
        settings.cache_enabled = False
        cache = CacheManager(redis_client=fake_redis, settings=settings)
        
        result = await cache.get("any_key")
        assert result["status"] == "disabled"

    @pytest.mark.asyncio
    async def test_cache_miss_on_empty(self, fake_redis, test_settings):
        """Cache returns miss for non-existent key."""
        cache = CacheManager(redis_client=fake_redis, settings=test_settings)
        
        result = await cache.get("nonexistent_key")
        assert result["status"] == "miss"
        assert result["value"] is None

    @pytest.mark.asyncio
    async def test_cache_roundtrip(self, fake_redis, test_settings):
        """Basic cache set and get."""
        cache = CacheManager(redis_client=fake_redis, settings=test_settings)

        await cache.set("test_key", "test_value", ttl=60)

        result = await cache.get("test_key")

        assert result["status"] == "hit"
        assert result["value"] == "test_value"
        assert result["ttl"] == 60
        assert result["cached_at"] is not None
        assert result["age_seconds"] is not None


class TestCacheTiming:
    @pytest.mark.asyncio
    async def test_age_calculation(self, fake_redis, test_settings):
        """Verify age is calculated correctly with frozen time."""
        cache = CacheManager(redis_client=fake_redis, settings=test_settings)

        with freeze_time("2020-01-01 00:00:00"):
            await cache.set("test_key", "test_value", ttl=60)

        with freeze_time("2020-01-01 00:00:45"):
            result = await cache.get("test_key")
            assert result["status"] == "hit"
            assert result["value"] == "test_value"
            assert result["age_seconds"] == 45.0

    @pytest.mark.asyncio
    async def test_age_at_different_offsets(self, fake_redis, test_settings):
        """Test age calculation at various time offsets."""
        cache = CacheManager(redis_client=fake_redis, settings=test_settings)
        
        with freeze_time("2020-01-01 10:00:00"):
            # Use a longer TTL (2 hours) so it doesn't expire during test
            await cache.set("key", "value", ttl=7200)
        
        # Check at T+1 minute
        with freeze_time("2020-01-01 10:01:00"):
            result = await cache.get("key")
            assert result["age_seconds"] == 60.0
        
        # Check at T+5 minutes
        with freeze_time("2020-01-01 10:05:00"):
            result = await cache.get("key")
            assert result["age_seconds"] == 300.0
        
        # Check at T+1 hour
        with freeze_time("2020-01-01 11:00:00"):
            result = await cache.get("key")
            assert result["age_seconds"] == 3600.0

    @pytest.mark.asyncio
    async def test_cached_at_timestamp(self, fake_redis, test_settings):
        """Verify cached_at timestamp is correct."""
        cache = CacheManager(redis_client=fake_redis, settings=test_settings)
        
        with freeze_time("2020-01-01 15:30:00"):
            await cache.set("key", "value")
            # Get immediately while still frozen in time
            result = await cache.get("key")
            assert "2020-01-01" in result["cached_at"]
            assert "15:30:00" in result["cached_at"]


class TestCacheTTL:
    @pytest.mark.asyncio
    async def test_ttl_capping(self, fake_redis, test_settings):
        """Verify TTL is capped at max_ttl."""
        cache = CacheManager(redis_client=fake_redis, settings=test_settings)

        await cache.set("test_key", "test_value", ttl=9999)

        result = await cache.get("test_key")
        assert result["status"] == "hit"
        assert result["ttl"] == test_settings.cache_max_ttl  # Capped at 3600

        # Verify Redis TTL was also capped
        redis_ttl = await fake_redis.ttl(f"{test_settings.cache_key_prefix}:test_key")
        assert redis_ttl <= test_settings.cache_max_ttl
        assert redis_ttl > 0  # Should be set

    @pytest.mark.asyncio
    async def test_ttl_default(self, fake_redis, test_settings):
        """Verify default TTL is used when not specified."""
        cache = CacheManager(redis_client=fake_redis, settings=test_settings)
        
        await cache.set("key", "value")  # No TTL specified
        
        result = await cache.get("key")
        assert result["ttl"] == test_settings.cache_default_ttl

    @pytest.mark.asyncio
    async def test_ttl_values(self, fake_redis, test_settings):
        """Test various TTL values."""
        cache = CacheManager(redis_client=fake_redis, settings=test_settings)
        
        test_cases = [
            (100, 100),       # Under max - not capped
            (300, 300),       # At default - not capped
            (3600, 3600),     # At max - not capped
            (9999, 3600),     # Over max - capped
            (None, 300),      # None - uses default
        ]
        
        for ttl_input, expected_ttl in test_cases:
            key = f"key_{ttl_input}"
            await cache.set(key, "value", ttl=ttl_input)
            
            result = await cache.get(key)
            assert result["ttl"] == expected_ttl, f"TTL mismatch for input {ttl_input}"


class TestCacheKeyGeneration:
    def test_key_normalization_whitespace(self, fake_redis, test_settings):
        """Verify whitespace is normalized in keys."""
        cache = CacheManager(redis_client=fake_redis, settings=test_settings)
        
        key1 = cache.generate_cache_key("router1", "show ip int brief")
        key2 = cache.generate_cache_key("router1", "show  ip   int  brief")
        key3 = cache.generate_cache_key("router1", "  show ip int brief  ")
        
        assert key1 == key2 == key3

    def test_key_deterministic(self, fake_redis, test_settings):
        """Verify same inputs produce same key."""
        cache = CacheManager(redis_client=fake_redis, settings=test_settings)
        
        key1 = cache.generate_cache_key("router1", "show version")
        key2 = cache.generate_cache_key("router1", "show version")
        
        assert key1 == key2

    def test_key_different_commands(self, fake_redis, test_settings):
        """Verify different commands produce different keys."""
        cache = CacheManager(redis_client=fake_redis, settings=test_settings)
        
        key1 = cache.generate_cache_key("router1", "show version")
        key2 = cache.generate_cache_key("router1", "show ip int brief")
        
        assert key1 != key2

    def test_key_different_devices(self, fake_redis, test_settings):
        """Verify different devices produce different keys."""
        cache = CacheManager(redis_client=fake_redis, settings=test_settings)
        
        key1 = cache.generate_cache_key("router1", "show version")
        key2 = cache.generate_cache_key("router2", "show version")
        
        assert key1 != key2


class TestDeviceInvalidation:
    @pytest.mark.asyncio
    async def test_invalidate_device(self, fake_redis, test_settings):
        """Verify device invalidation clears only that device's cache."""
        cache = CacheManager(redis_client=fake_redis, settings=test_settings)
        
        # Cache entries for multiple devices
        await cache.set("router1:cmd1:hash1", "output1")
        await cache.set("router1:cmd2:hash2", "output2")
        await cache.set("router2:cmd1:hash3", "output3")
        
        # Invalidate router1
        deleted = await cache.invalidate_device("router1")
        
        assert deleted == 2  # Two router1 entries deleted
        
        # router1 entries gone
        assert (await cache.get("router1:cmd1:hash1"))["status"] == "miss"
        assert (await cache.get("router1:cmd2:hash2"))["status"] == "miss"
        
        # router2 entry still there
        assert (await cache.get("router2:cmd1:hash3"))["status"] == "hit"

    @pytest.mark.asyncio
    async def test_invalidate_nonexistent_device(self, fake_redis, test_settings):
        """Verify invalidating non-existent device doesn't error."""
        cache = CacheManager(redis_client=fake_redis, settings=test_settings)
        
        deleted = await cache.invalidate_device("nonexistent_device")
        assert deleted == 0


class TestCacheClearAll:
    @pytest.mark.asyncio
    async def test_clear_all(self, fake_redis, test_settings):
        """Verify clear_all removes all cache entries."""
        cache = CacheManager(redis_client=fake_redis, settings=test_settings)
        
        # Add multiple entries
        await cache.set("key1", "value1")
        await cache.set("key2", "value2")
        await cache.set("key3", "value3")
        
        # Clear all
        deleted = await cache.clear_all()
        
        assert deleted == 3
        
        # All gone
        assert (await cache.get("key1"))["status"] == "miss"
        assert (await cache.get("key2"))["status"] == "miss"
        assert (await cache.get("key3"))["status"] == "miss"
