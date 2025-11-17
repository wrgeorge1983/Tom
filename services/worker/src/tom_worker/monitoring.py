"""Monitoring functionality for Tom Worker."""

import asyncio
import json
import logging
import os
import socket
import time
from typing import Any, Dict, Optional

import redis.asyncio as redis

logger = logging.getLogger(__name__)


async def heartbeat_task(
    redis_client: redis.Redis,
    worker_id: str,
    shutdown_event: asyncio.Event,
    version: str = "unknown"
) -> None:
    """Send periodic heartbeats to indicate worker is alive.
    
    Args:
        redis_client: Redis client for sending heartbeats
        worker_id: Unique identifier for this worker
        shutdown_event: Event to signal when to stop heartbeats
        version: Worker version string
    """
    hostname = socket.gethostname()
    pid = os.getpid()
    
    logger.info(f"Starting heartbeat task for worker {worker_id}")
    
    while not shutdown_event.is_set():
        try:
            heartbeat_data = {
                "worker_id": worker_id,
                "hostname": hostname,
                "timestamp": time.time(),
                "version": version,
                "status": "healthy",
                "pid": pid,
                # TODO: Add current_jobs count when we have access to it
            }
            
            # Set heartbeat with 60 second TTL
            await redis_client.setex(
                f"tom:worker:heartbeat:{worker_id}",
                60,  # TTL in seconds
                json.dumps(heartbeat_data)
            )
            
            logger.debug(f"Heartbeat sent for worker {worker_id}")
            
        except Exception as e:
            logger.error(f"Failed to send heartbeat: {e}")
        
        # Wait 30 seconds before next heartbeat
        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=30.0)
        except asyncio.TimeoutError:
            # Timeout is expected - means we should send another heartbeat
            pass
    
    logger.info(f"Heartbeat task stopped for worker {worker_id}")


def classify_error(error: Optional[str]) -> str:
    """Classify an error string into categories for metrics.
    
    Args:
        error: Error message or exception string
        
    Returns:
        Error type: 'auth', 'gating', 'timeout', 'network', or 'other'
    """
    if not error:
        return "other"
    
    error_lower = error.lower()
    
    if any(term in error_lower for term in ["auth", "password", "credential", "permission"]):
        return "auth"
    elif any(term in error_lower for term in ["gating", "busy", "lease"]):
        return "gating"
    elif any(term in error_lower for term in ["timeout", "timed out"]):
        return "timeout"
    elif any(term in error_lower for term in ["connection", "network", "unreachable"]):
        return "network"
    else:
        return "other"


async def record_job_stats(
    redis_client: redis.Redis,
    worker_id: str,
    device: str,
    status: str,
    error: Optional[str] = None,
    duration: Optional[float] = None,
    job_id: Optional[str] = None,
    credential_id: Optional[str] = None,
    command: Optional[str] = None,
    attempts: int = 1
) -> None:
    """Record job completion statistics to Redis.
    
    Stats are stored with 1-hour TTL for collection by controller.
    
    Args:
        redis_client: Redis client
        worker_id: Worker identifier
        device: Device name
        status: 'success' or 'failed'
        error: Error message if failed
        duration: Job duration in seconds
        job_id: Job identifier
        credential_id: Credential ID used (not the actual credential)
        command: Command executed (for failure tracking)
        attempts: Number of attempts made
    """
    STATS_TTL = 3600  # 1 hour TTL for stats
    
    try:
        # Classify error type if failed
        error_type = classify_error(error) if status == "failed" else None
        
        # Update worker stats
        worker_key = f"tom:stats:worker:{worker_id}"
        if status == "success":
            await redis_client.hincrby(worker_key, "complete", 1)  # type: ignore
        else:
            await redis_client.hincrby(worker_key, "failed", 1)  # type: ignore
            if error_type:
                await redis_client.hincrby(worker_key, f"{error_type}_failed", 1)  # type: ignore
        await redis_client.expire(worker_key, STATS_TTL)  # type: ignore[misc]
        
        # Update device stats
        device_key = f"tom:stats:device:{device}"
        if status == "success":
            await redis_client.hincrby(device_key, "complete", 1)  # type: ignore
        else:
            await redis_client.hincrby(device_key, "failed", 1)  # type: ignore
            if error_type:
                await redis_client.hincrby(device_key, f"{error_type}_failed", 1)  # type: ignore
        await redis_client.expire(device_key, STATS_TTL)  # type: ignore
        
        # Update global stats
        global_key = "tom:stats:global"
        if status == "success":
            await redis_client.hincrby(global_key, "complete", 1)  # type: ignore
        else:
            await redis_client.hincrby(global_key, "failed", 1)  # type: ignore
            if error_type:
                await redis_client.hincrby(global_key, f"{error_type}_failed", 1)  # type: ignore
        await redis_client.expire(global_key, STATS_TTL)  # type: ignore
        
        # Log to time-series stream for graphing
        stream_data = {
            "timestamp": int(time.time()),
            "worker": worker_id,
            "device": device,
            "status": status,
            "error_type": error_type or "none"
        }
        if duration is not None:
            stream_data["duration"] = duration
            
        await redis_client.xadd(
            "tom:metrics:stream",
            stream_data,  # type: ignore
            maxlen=10000  # Keep last 10k events
        )
        
        # If failed, also log to failed commands stream
        if status == "failed":
            await redis_client.xadd(
                "tom:failed_commands",
                {
                    "device": device,
                    "command": (command[:500] if command else "unknown"),  # Limit command length
                    "error": (error or "Unknown error")[:1000],  # Limit error length
                    "error_type": error_type or "other",
                    "job_id": job_id or "",
                    "worker_id": worker_id,
                    "credential_id": credential_id or "",
                    "attempts": attempts,
                    "timestamp": int(time.time())
                },
                maxlen=1000  # Keep last 1000 failures
            )
            
        logger.debug(f"Recorded stats: worker={worker_id}, device={device}, status={status}")
        
    except Exception as e:
        logger.error(f"Failed to record job stats: {e}")