import asyncio
import signal
import logging

import redis.asyncio as redis
import saq, saq.types

from tom_worker.credentials.credentials import YamlCredentialStore
from tom_worker.exceptions import GatingException, TransientException
from tom_worker.jobs import foo, send_commands_netmiko, send_commands_scrapli
from .config import settings

queue = saq.Queue.from_url(settings.redis_url)


async def main():
    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()

    match settings.credential_store:
        case "yaml":
            credential_store = YamlCredentialStore(settings.credential_path)

        case "vault":
            from tom_worker.credentials.vault import VaultCredentialStore, VaultClient

            vault_client = VaultClient.from_settings(settings)
            await vault_client.validate_access()
            credential_store = VaultCredentialStore(vault_client)

        case _:
            raise ValueError(f"Unknown credential store: {settings.credential_store}")

    semaphore_redis_client = redis.from_url(settings.redis_url)

    def worker_setup(ctx: saq.types.Context):
        ctx["credential_store"] = credential_store
        ctx["redis_client"] = semaphore_redis_client

    def should_retry(exception, attempts):
        if isinstance(exception, GatingException):
            return attempts < 10
        if isinstance(exception, TransientException):
            return attempts < 3
        return False

    worker = saq.Worker(
        queue,
        functions=[foo, send_commands_netmiko, send_commands_scrapli],
        startup=worker_setup,
    )
    print("worker built")

    def signal_handler(sig, frame):
        logging.info(f"Received signal {sig}. Shutting down.")
        worker.stop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler, sig, None)
    print("signals added")
    try:
        await worker.queue.connect()
        print("connected")
        await worker.start()
        print("started")
    finally:
        await worker.queue.disconnect()

        # logging.info("Shutting down worker.")


def run():
    """entrypoint"""
    print("Starting worker.")
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
