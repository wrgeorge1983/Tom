import asyncio
import signal
import logging

import saq, saq.types

from services.worker.src.tom_worker.credentials.credentials import YamlCredentialStore
from services.worker.src.tom_worker.exceptions import TomException
from .config import settings
from .adapters import NetmikoAdapter, ScrapliAsyncAdapter
from shared.models import NetmikoSendCommandModel, ScrapliSendCommandModel


queue = saq.Queue.from_url(f"redis://{settings.redis_host}:{settings.redis_port}")


async def foo(*args, **kwargs):
    print(f"{args=}, {kwargs=}")
    raise TomException("foo")
    return {
        "foo": "bar",
        "baz": "qux",
    }


async def send_command_netmiko(ctx: saq.types.Context, json: str):
    assert "credential_store" in ctx, "Missing credential store in context."
    credential_store = ctx["credential_store"]
    model = NetmikoSendCommandModel.model_validate_json(json)
    async with NetmikoAdapter.from_model(model, credential_store) as adapter:
        return await adapter.send_command(model.command)


async def send_command_scrapli(ctx: saq.types.Context, json: str):
    assert "credential_store" in ctx, "Missing credential store in context."
    credential_store = ctx["credential_store"]
    model = ScrapliSendCommandModel.model_validate_json(json)
    async with ScrapliAsyncAdapter.from_model(model, credential_store) as adapter:
        return await adapter.send_command(model.command)


async def main():
    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()

    credential_store = YamlCredentialStore(settings.credential_path)

    worker = saq.Worker(
        queue,
        functions=[foo, send_command_netmiko, send_command_scrapli],
        startup=lambda ctx: ctx.__setitem__("credential_store", credential_store),
    )

    def signal_handler(sig, frame):
        logging.info(f"Received signal {sig}. Shutting down.")
        worker.stop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler, sig, None)

    try:
        await worker.queue.connect()
        await worker.start()
    finally:
        await worker.queue.disconnect()

        # logging.info("Shutting down worker.")


def run():
    """entrypoint"""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Received KeyboardInterrupt. Shutting down.")
    except asyncio.CancelledError:
        logging.info("Received CancelledError. Shutting down.")
    finally:
        logging.info("Shutting down.")


if __name__ == "__main__":
    run()
