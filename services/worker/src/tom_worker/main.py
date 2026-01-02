import asyncio
import signal
import logging
import sys
import uuid
from importlib.metadata import version as get_version

import redis.asyncio as redis
import saq, saq.types

from tom_shared.cache import CacheManager

from tom_worker.exceptions import TomException
from tom_worker.jobs import (
    foo,
    send_commands_netmiko,
    send_commands_scrapli,
    list_credentials,
)
from tom_worker.monitoring import heartbeat_task
from tom_worker.Plugins.base import CredentialPluginManager
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

    # Initialize credential plugin
    # This loads the specific plugin configured, checking dependencies and raising
    # clear errors if anything is wrong (missing module, missing deps, etc.)
    plugin_manager = CredentialPluginManager()
    try:
        credential_plugin = plugin_manager.initialize_credential_plugin(
            settings.credential_plugin, settings
        )
        logger.info(f"Loaded credential plugin: {settings.credential_plugin}")
    except ValueError as e:
        logger.error(
            f"Failed to load credential plugin '{settings.credential_plugin}': {e}"
        )
        raise SystemExit(1)

    # Validate the plugin (connectivity, auth, file existence, etc.)
    try:
        await credential_plugin.validate()
        logger.info(
            f"Credential plugin '{settings.credential_plugin}' validated successfully"
        )
    except TomException as e:
        logger.error(f"Credential plugin validation failed: {e}")
        raise SystemExit(1)

    semaphore_redis_client = redis.from_url(settings.redis_url)

    cache_redis = redis.from_url(
        settings.redis_url, decode_responses=True
    )  # needs decode_responses=True
    cache_manager = CacheManager(cache_redis, settings)

    # Start heartbeat task
    monitoring_redis = redis.from_url(settings.redis_url)
    worker_version = get_version("tom-worker")

    heartbeat_coro = heartbeat_task(
        monitoring_redis, worker_id, shutdown_event, version=worker_version
    )
    heartbeat_task_handle = asyncio.create_task(heartbeat_coro)
    logger.info(f"Started heartbeat task for worker {worker_id}")

    def worker_setup(ctx: saq.types.Context):
        ctx["credential_store"] = (
            credential_plugin  # CredentialPlugin has same interface
        )
        ctx["redis_client"] = semaphore_redis_client
        ctx["cache_manager"] = cache_manager
        ctx["settings"] = settings
        ctx["worker_id"] = worker_id
        ctx["monitoring_redis"] = monitoring_redis

    async def before_job_process(ctx: saq.types.Context):
        """Record job start time for duration tracking."""
        import time
        import json

        job = ctx.get("job")
        worker_id = ctx.get("worker_id", "unknown")

        ctx["job_start_time"] = time.time()

        # Extract job info for logging
        device = "unknown"
        commands = []
        if job and job.kwargs and "json" in job.kwargs:
            try:
                data = json.loads(job.kwargs["json"])
                device = data.get("host", "unknown")
                commands = data.get("commands", [])
            except Exception:
                pass

        logger.info(
            f"Worker {worker_id}: Starting job {job.id if job else 'unknown'} "
            f"[{job.function if job else 'unknown'}] for device {device} "
            f"(attempt {job.attempts if job else '?'}, "
            f"commands: {len(commands)})"
        )

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
                logger.debug(
                    f"Extracted from job: device={device}, commands={commands[:3] if commands else 'none'}"
                )
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

        # Log job completion
        if status == "success":
            logger.info(
                f"Worker {worker_id}: Completed job {job.id} "
                f"for device {device} in {duration:.2f}s "
                f"(attempt {job.attempts})"
            )
        else:
            # Extract error summary for logging
            error_summary = "Unknown error"
            if error:
                # Get last line of error which usually has the actual exception
                error_lines = error.strip().split("\n")
                if error_lines:
                    error_summary = error_lines[-1][:200]

            logger.error(
                f"Worker {worker_id}: FAILED job {job.id} "
                f"for device {device} after {duration:.2f}s "
                f"(attempt {job.attempts}): {error_summary}"
            )

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
            attempts=job.attempts,
        )

    worker = saq.Worker(
        queue,
        functions=[foo, send_commands_netmiko, send_commands_scrapli, list_credentials],
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
