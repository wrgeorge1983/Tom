import logging
import saq.types

from tom_worker.adapters import NetmikoAdapter, ScrapliAsyncAdapter
from tom_worker.config import Settings
from tom_worker.semaphore import device_lease
from tom_shared.models import (
    NetmikoSendCommandModel,
    ScrapliSendCommandModel,
    CommandExecutionResult,
)
from tom_shared.cache import CacheManager

logger = logging.getLogger(__name__)


async def foo(*args, **kwargs):
    return {
        "foo": "bar",
        "baz": "qux",
    }


async def list_credentials(ctx: saq.types.Context):
    """List all available credential IDs from the configured credential store.

    :param ctx: SAQ context containing credential_store
    :return: Dictionary with list of credential IDs
    """
    assert "credential_store" in ctx, "Missing credential store in context."
    credential_store = ctx["credential_store"]

    job_id = ctx["job"].id
    logger.info(f"Job {job_id}: Listing credentials")

    credentials = await credential_store.list_credentials()

    logger.info(f"Job {job_id}: Found {len(credentials)} credential(s)")
    return {"credentials": credentials}


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
    cache_ttl = (
        model.cache_ttl if model.cache_ttl is not None else settings.cache_default_ttl
    )

    results = {}
    cache_metadata = {"cache_status": "miss", "commands": {}}

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
                        "ttl": cache_ttl,
                    }
                else:
                    needed_commands.append(command)
                    cache_metadata["commands"][command] = {"cache_status": "miss"}
            except Exception as e:
                logger.warning(f"Failed to get cache entry {cache_key}: {e}")
                needed_commands.append(command)
                cache_metadata["commands"][command] = {"cache_status": "error"}
    else:
        needed_commands = model.commands

    if len(needed_commands) == 0:
        cache_metadata["cache_status"] = "hit"
    elif len(needed_commands) == len(model.commands):
        cache_metadata["cache_status"] = "miss"
    else:
        cache_metadata["cache_status"] = "partial"

    if needed_commands:
        async with device_lease(
            ctx, redis_client, device_id, job_id, model.max_queue_wait
        ):
            logger.info(
                f"Job {job_id}: Executing {len(needed_commands)} command(s) on {device_id} "
                f"[netmiko/{model.device_type}]"
            )

            async with await NetmikoAdapter.from_model(
                model, credential_store
            ) as adapter:
                result = await adapter.send_commands(needed_commands)
                if use_cache:
                    for command, value in result.items():
                        cache_key = cache_manager.generate_cache_key(
                            model.host, command
                        )
                        await cache_manager.set(cache_key, value, ttl=cache_ttl)

                results.update(result)

            logger.debug(
                f"Job {job_id}: Successfully executed {len(needed_commands)} command(s) on {device_id}"
            )

    # Create structured result with metadata
    execution_result = CommandExecutionResult(
        data={command: results[command] for command in model.commands},
        meta={"cache": cache_metadata},
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
    cache_ttl = (
        model.cache_ttl if model.cache_ttl is not None else settings.cache_default_ttl
    )

    results = {}
    cache_metadata = {"cache_status": "miss", "commands": {}}

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
                        "ttl": cache_ttl,
                    }
                else:
                    needed_commands.append(command)
                    cache_metadata["commands"][command] = {"cache_status": "miss"}
            except Exception as e:
                logger.warning(f"Failed to get cache entry {cache_key}: {e}")
                needed_commands.append(command)
                cache_metadata["commands"][command] = {"cache_status": "error"}
    else:
        needed_commands = model.commands

    if len(needed_commands) == 0:
        cache_metadata["cache_status"] = "hit"
    elif len(needed_commands) == len(model.commands):
        cache_metadata["cache_status"] = "miss"
    else:
        cache_metadata["cache_status"] = "partial"

    if needed_commands:
        async with device_lease(
            ctx, redis_client, device_id, job_id, model.max_queue_wait
        ):
            logger.info(
                f"Job {job_id}: Executing {len(needed_commands)} command(s) on {device_id} "
                f"[scrapli/{model.device_type}]"
            )

            async with await ScrapliAsyncAdapter.from_model(
                model, credential_store
            ) as adapter:
                result = await adapter.send_commands(needed_commands)
                if use_cache:
                    for command, value in result.items():
                        cache_key = cache_manager.generate_cache_key(
                            model.host, command
                        )
                        await cache_manager.set(cache_key, value, ttl=cache_ttl)

                results.update(result)

            logger.debug(
                f"Job {job_id}: Successfully executed {len(needed_commands)} command(s) on {device_id}"
            )

    # Create structured result with metadata
    execution_result = CommandExecutionResult(
        data={command: results[command] for command in model.commands},
        meta={"cache": cache_metadata},
    )

    # Return as dict for SAQ serialization
    return execution_result.model_dump()
