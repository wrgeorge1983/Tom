import saq.types

from tom_worker.adapters import NetmikoAdapter, ScrapliAsyncAdapter
from tom_worker.exceptions import GatingException
from tom_worker.semaphore import DeviceSemaphore
from tom_shared.models import NetmikoSendCommandModel, ScrapliSendCommandModel


async def foo(*args, **kwargs):
    print(f"{args=}, {kwargs=}")
    return {
        "foo": "bar",
        "baz": "qux",
    }


async def send_commands_netmiko(ctx: saq.types.Context, json: str):
    print(f"attempting send_command_netmiko: {ctx['job'].id=}")
    assert "credential_store" in ctx, "Missing credential store in context."
    credential_store = ctx["credential_store"]
    redis_client = ctx["redis_client"]
    model = NetmikoSendCommandModel.model_validate_json(json)

    job_id = ctx["job"].id

    device_id = f"{model.host}:{model.port}"
    semaphore = DeviceSemaphore(redis_client=redis_client, device_id=device_id)
    if not await semaphore.acquire_lease(job_id):
        raise GatingException(f"{device_id} busy. Lease not acquired.")

    try:
        async with await NetmikoAdapter.from_model(model, credential_store) as adapter:
            result = await adapter.send_commands(model.commands)

        print(f"completed send_command_netmiko: {ctx['job'].id=}")
        return result
    finally:
        await semaphore.release_lease(job_id)


async def send_commands_scrapli(ctx: saq.types.Context, json: str):
    print("running send_command_scrapli")
    assert "credential_store" in ctx, "Missing credential store in context."
    credential_store = ctx["credential_store"]
    redis_client = ctx["redis_client"]
    model = ScrapliSendCommandModel.model_validate_json(json)

    job_id = ctx["job"].id
    device_id = f"{model.host}:{model.port}"
    semaphore = DeviceSemaphore(redis_client=redis_client, device_id=device_id)
    if not await semaphore.acquire_lease(job_id):
        raise GatingException(f"{device_id} busy. Lease not acquired.")

    try:
        async with await ScrapliAsyncAdapter.from_model(
            model, credential_store
        ) as adapter:
            result = await adapter.send_commands(model.commands)
        return result
    finally:
        await semaphore.release_lease(job_id)
