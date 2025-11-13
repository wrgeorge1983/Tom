import asyncio
import signal
import logging
import sys
import uuid

import redis.asyncio as redis
import saq, saq.types

from tom_shared.cache import CacheManager

from tom_worker.credentials.credentials import YamlCredentialStore
from tom_worker.exceptions import GatingException, TransientException
from tom_worker.jobs import foo, send_commands_netmiko, send_commands_scrapli
from tom_worker.monitoring import heartbeat_task
from .config import settings

# Configure logging before creating the queue
logging.basicConfig(
    level=settings.log_level,  # Set root to DEBUG
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger(__name__)

# Enable debug logging for SAQ
saq_logger = logging.getLogger("saq")
saq_logger.setLevel(settings.log_level)

queue = saq.Queue.from_url(settings.redis_url)




async def main():
    logger.info("Starting worker main function")
    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()
    
    # Generate unique worker ID
    worker_id = f"worker-{uuid.uuid4().hex[:8]}"
    logger.info(f"Worker ID: {worker_id}")

    match settings.credential_store:
        case "yaml":
            logger.info(f"Using YAML credential store from {settings.credential_path}")
            credential_store = YamlCredentialStore(settings.credential_path)

        case "vault":
            logger.info("Using Vault credential store")
            from tom_worker.credentials.vault import VaultCredentialStore, VaultClient

            vault_client = await VaultClient.from_settings(settings)
            await vault_client.validate_access()
            credential_store = VaultCredentialStore(vault_client)

        case _:
            raise ValueError(f"Unknown credential store: {settings.credential_store}")

    semaphore_redis_client = redis.from_url(settings.redis_url)

    cache_redis = redis.from_url(settings.redis_url, decode_responses=True)  # needs decode_responses=True
    cache_manager = CacheManager(cache_redis, settings)
    
    # Start heartbeat task
    monitoring_redis = redis.from_url(settings.redis_url)
    heartbeat_coro = heartbeat_task(
        monitoring_redis,
        worker_id,
        shutdown_event,
        version="0.10.0"
    )
    heartbeat_task_handle = asyncio.create_task(heartbeat_coro)
    logger.info(f"Started heartbeat task for worker {worker_id}")

    def worker_setup(ctx: saq.types.Context):
        ctx["credential_store"] = credential_store
        ctx["redis_client"] = semaphore_redis_client
        ctx["cache_manager"] = cache_manager
        ctx["settings"] = settings
        ctx["worker_id"] = worker_id
        ctx["monitoring_redis"] = monitoring_redis

    async def before_job_process(ctx: saq.types.Context):
        """Record job start time for duration tracking."""
        import time
        ctx["job_start_time"] = time.time()

    async def after_job_process(ctx: saq.types.Context):
        """Record job stats after processing."""
        from tom_worker.monitoring import record_job_stats
        import time
        
        job = ctx["job"]
        worker_id = ctx["worker_id"]
        monitoring_redis = ctx["monitoring_redis"]
        
        # Extract device from job kwargs if available
        device = "unknown"
        credential_id = None
        command = None
        
        # Try to extract info from job kwargs
        if job.kwargs and "json" in job.kwargs:
            try:
                import json
                data = json.loads(job.kwargs["json"])
                device = data.get("host", "unknown")
                credential_id = data.get("credential_id")
                commands = data.get("commands", [])
                if commands:
                    command = ", ".join(commands[:3])  # First 3 commands
                logger.debug(f"Extracted from job: device={device}, commands={commands[:3] if commands else 'none'}")
            except Exception as e:
                logger.debug(f"Failed to extract job info: {e}")
                pass  # Fallback to defaults
        else:
            logger.debug(f"No json in job.kwargs: {job.kwargs}")
        
        # Determine status and error
        status = "success" if job.status == "complete" else "failed"
        error = str(job.error) if job.error else None
        
        # Calculate duration
        duration = None
        if "job_start_time" in ctx:
            duration = time.time() - ctx["job_start_time"]
        
        # Record stats
        await record_job_stats(
            monitoring_redis,
            worker_id,
            device,
            status,
            error=error,
            duration=duration,
            job_id=job.id,
            credential_id=credential_id,
            command=command,
            attempts=job.attempts
        )

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
        before_process=before_job_process,
        after_process=after_job_process,
    )

    logger.info("Worker instance created")

    def signal_handler(sig, frame):
        logger.info(f"Received signal {sig}. Shutting down.")
        shutdown_event.set()  # Signal heartbeat to stop
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
        
        # Clean up heartbeat task
        shutdown_event.set()
        try:
            await asyncio.wait_for(heartbeat_task_handle, timeout=5.0)
        except asyncio.TimeoutError:
            logger.warning("Heartbeat task did not shutdown cleanly")
            heartbeat_task_handle.cancel()
            
        # Close monitoring Redis connection
        await monitoring_redis.close()
        
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
