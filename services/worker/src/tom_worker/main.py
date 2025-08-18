import asyncio
import signal
import logging

import redis.asyncio as redis
import saq, saq.types

from services.worker.src.tom_worker.credentials.credentials import YamlCredentialStore
from services.worker.src.tom_worker.exceptions import GatingException, TransientException
from services.worker.src.tom_worker.jobs import foo, send_command_netmiko, send_command_scrapli
from .config import settings

queue = saq.Queue.from_url(f"redis://{settings.redis_host}:{settings.redis_port}")


async def main():
    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()

    credential_store = YamlCredentialStore(settings.credential_path)
    semaphore_redis_client = redis.from_url(f"redis://{settings.redis_host}:{settings.redis_port}")

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
        functions=[foo, send_command_netmiko, send_command_scrapli],
        startup=worker_setup,
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
