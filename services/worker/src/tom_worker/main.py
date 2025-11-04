import asyncio
import signal
import logging
import sys

import redis.asyncio as redis
import saq, saq.types

from shared.tom_shared.cache import CacheManager

from tom_worker.credentials.credentials import YamlCredentialStore
from tom_worker.exceptions import GatingException, TransientException
from tom_worker.jobs import foo, send_commands_netmiko, send_commands_scrapli
from .config import settings

# Configure logging before creating the queue
logging.basicConfig(
    level=logging.DEBUG,  # Set root to DEBUG
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger(__name__)

# Enable debug logging for SAQ
saq_logger = logging.getLogger("saq")
saq_logger.setLevel(logging.DEBUG)

queue = saq.Queue.from_url(settings.redis_url)




async def main():
    logger.info("Starting worker main function")
    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()

    match settings.credential_store:
        case "yaml":
            logger.info(f"Using YAML credential store from {settings.credential_path}")
            credential_store = YamlCredentialStore(settings.credential_path)

        case "vault":
            logger.info("Using Vault credential store")
            from tom_worker.credentials.vault import VaultCredentialStore, VaultClient

            vault_client = VaultClient.from_settings(settings)
            await vault_client.validate_access()
            credential_store = VaultCredentialStore(vault_client)

        case _:
            raise ValueError(f"Unknown credential store: {settings.credential_store}")

    semaphore_redis_client = redis.from_url(settings.redis_url)

    cache_redis = redis.from_url(settings.redis_url, decode_responses=True)  # needs decode_responses=True
    cache_manager = CacheManager(cache_redis, settings)

    def worker_setup(ctx: saq.types.Context):
        ctx["credential_store"] = credential_store
        ctx["redis_client"] = semaphore_redis_client
        ctx["cache_manager"] = cache_manager

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
    logger.info("Worker instance created")

    def signal_handler(sig, frame):
        logger.info(f"Received signal {sig}. Shutting down.")
        worker.stop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler, sig, None)
    logger.info("Signal handlers registered")
    try:
        await worker.queue.connect()
        logger.info("Connected to Redis queue")
        logger.info("Starting worker (this will block until shutdown)")
        await worker.start()
        logger.info("Worker has stopped")
    finally:
        logger.info("Disconnecting from queue")
        await worker.queue.disconnect()
        logger.info("Cleanup complete")


def run():
    """entrypoint"""
    logger.info("Worker entrypoint started")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Received KeyboardInterrupt. Shutting down.")
    except asyncio.CancelledError:
        logger.info("Received CancelledError. Shutting down.")
    finally:
        logger.info("Worker shutdown complete")


if __name__ == "__main__":
    run()
