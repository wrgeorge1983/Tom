import logging
import saq.types

from tom_worker.adapters import NetmikoAdapter, ScrapliAsyncAdapter
from tom_worker.config import Settings
from tom_worker.exceptions import GatingException
from tom_worker.semaphore import DeviceSemaphore
from shared.tom_shared.models import (
    NetmikoSendCommandModel, 
    ScrapliSendCommandModel,
    CommandExecutionResult
)
from shared.tom_shared.cache import CacheManager

logger = logging.getLogger(__name__)


async def foo(*args, **kwargs):
    return {
        "foo": "bar",
        "baz": "qux",
    }


async def send_commands_netmiko(ctx: saq.types.Context, json: str):
    assert "credential_store" in ctx, "Missing credential store in context."
    settings: Settings = ctx["settings"]
    credential_store = ctx["credential_store"]
    redis_client = ctx["redis_client"]
    cache_manager: CacheManager = ctx["cache_manager"]

    model = NetmikoSendCommandModel.model_validate_json(json)

    job_id = ctx["job"].id

    device_id = f"{model.host}:{model.port}"

    use_cache = model.use_cache
    cache_refresh = model.cache_refresh
    cache_ttl = model.cache_ttl if model.cache_ttl is not None else settings.cache_default_ttl

    results = {}
    cache_metadata = {
        "cache_status": "miss",
        "commands": {}
    }

    needed_commands = []

    if use_cache and not cache_refresh:
        for command in model.commands:
            cache_key = cache_manager.generate_cache_key(model.host, command)
            try:
                cache_result = await cache_manager.get(cache_key)
                if cache_result["status"] == "hit":
                    results[command] = cache_result["value"]
                    cache_metadata["commands"][command] = {
                        "cache_status": "hit",
                        "cached_at": cache_result["cached_at"],
                        "age_seconds": cache_result["age_seconds"],
                        "ttl": cache_ttl
                    }
                else:
                    needed_commands.append(command)
                    cache_metadata["commands"][command] = {
                        "cache_status": "miss"
                    }
            except Exception as e:
                logger.warning(f"Failed to get cache entry {cache_key}: {e}")
                needed_commands.append(command)
                cache_metadata["commands"][command] = {
                    "cache_status": "error"
                }
    else:
        needed_commands = model.commands

    if len(needed_commands) == 0:
        cache_metadata["cache_status"] = "hit"
    elif len(needed_commands) == len(model.commands):
        cache_metadata["cache_status"] = "miss"
    else:
        cache_metadata["cache_status"] = "partial"

    if needed_commands:
        semaphore = DeviceSemaphore(redis_client=redis_client, device_id=device_id)
        if not await semaphore.acquire_lease(job_id):
            raise GatingException(f"{device_id} busy. Lease not acquired.")

        try:
            async with await NetmikoAdapter.from_model(model, credential_store) as adapter:
                result = await adapter.send_commands(needed_commands)
                if use_cache:
                    for command, value in result.items():
                        cache_key = cache_manager.generate_cache_key(model.host, command)
                        await cache_manager.set(cache_key, value, ttl=cache_ttl)

                results.update(result)
        finally:
            await semaphore.release_lease(job_id)

    # Create structured result with metadata
    execution_result = CommandExecutionResult(
        data={command: results[command] for command in model.commands},
        meta={"cache": cache_metadata}
    )
    
    # Return as dict for SAQ serialization
    return execution_result.model_dump()


async def send_commands_scrapli(ctx: saq.types.Context, json: str):
    assert "credential_store" in ctx, "Missing credential store in context."
    settings: Settings = ctx["settings"]
    credential_store = ctx["credential_store"]
    redis_client = ctx["redis_client"]
    cache_manager: CacheManager = ctx["cache_manager"]

    model = ScrapliSendCommandModel.model_validate_json(json)

    job_id = ctx["job"].id
    device_id = f"{model.host}:{model.port}"

    use_cache = model.use_cache
    cache_refresh = model.cache_refresh
    cache_ttl = model.cache_ttl if model.cache_ttl is not None else settings.cache_default_ttl

    results = {}
    cache_metadata = {
        "cache_status": "miss",
        "commands": {}
    }

    needed_commands = []

    if use_cache and not cache_refresh:
        for command in model.commands:
            cache_key = cache_manager.generate_cache_key(model.host, command)
            try:
                cache_result = await cache_manager.get(cache_key)
                if cache_result["status"] == "hit":
                    results[command] = cache_result["value"]
                    cache_metadata["commands"][command] = {
                        "cache_status": "hit",
                        "cached_at": cache_result["cached_at"],
                        "age_seconds": cache_result["age_seconds"],
                        "ttl": cache_ttl
                    }
                else:
                    needed_commands.append(command)
                    cache_metadata["commands"][command] = {
                        "cache_status": "miss"
                    }
            except Exception as e:
                logger.warning(f"Failed to get cache entry {cache_key}: {e}")
                needed_commands.append(command)
                cache_metadata["commands"][command] = {
                    "cache_status": "error"
                }
    else:
        needed_commands = model.commands

    if len(needed_commands) == 0:
        cache_metadata["cache_status"] = "hit"
    elif len(needed_commands) == len(model.commands):
        cache_metadata["cache_status"] = "miss"
    else:
        cache_metadata["cache_status"] = "partial"

    if needed_commands:
        semaphore = DeviceSemaphore(redis_client=redis_client, device_id=device_id)
        if not await semaphore.acquire_lease(job_id):
            raise GatingException(f"{device_id} busy. Lease not acquired.")

        try:
            async with await ScrapliAsyncAdapter.from_model(
                    model, credential_store
            ) as adapter:
                result = await adapter.send_commands(needed_commands)
                if use_cache:
                    for command, value in result.items():
                        cache_key = cache_manager.generate_cache_key(model.host, command)
                        await cache_manager.set(cache_key, value, ttl=cache_ttl)

                results.update(result)
        finally:
            await semaphore.release_lease(job_id)

    # Create structured result with metadata
    execution_result = CommandExecutionResult(
        data={command: results[command] for command in model.commands},
        meta={"cache": cache_metadata}
    )
    
    # Return as dict for SAQ serialization
    return execution_result.model_dump()