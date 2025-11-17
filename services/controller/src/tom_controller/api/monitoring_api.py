"""Monitoring API endpoints for Tom Controller."""

import json
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

# Auth dependency will be added at router registration in app.py
# to avoid circular imports
# These endpoints expose sensitive operational data (failed commands, error traces, etc.)
router = APIRouter(
    prefix="/monitoring",
    tags=["monitoring"]
)


async def get_redis_client(request: Request) -> aioredis.Redis:
    """Get Redis client from app state."""
    return request.app.state.redis_client


@router.get("/workers")
async def get_workers(
    redis: aioredis.Redis = Depends(get_redis_client)
) -> Dict[str, Any]:
    """Get status of all workers.
    
    Returns information about active workers based on heartbeats.
    """
    workers = []
    
    try:
        # Scan for worker heartbeats
        async for key in redis.scan_iter(match="tom:worker:heartbeat:*"):
            # Parse worker ID from key
            key_str = key.decode() if isinstance(key, bytes) else key
            parts = key_str.split(":")
            if len(parts) >= 4:
                worker_id = parts[3]
                
                # Get heartbeat data
                heartbeat_raw = await redis.get(key)
                if heartbeat_raw:
                    try:
                        heartbeat = json.loads(heartbeat_raw)
                        
                        # Calculate time since last heartbeat
                        last_seen = datetime.fromtimestamp(heartbeat.get("timestamp", 0))
                        now = datetime.now()
                        seconds_ago = (now - last_seen).total_seconds()
                        
                        # Determine status based on heartbeat age
                        if seconds_ago < 60:
                            status = "healthy"
                        elif seconds_ago < 180:
                            status = "stale"
                        else:
                            status = "unhealthy"
                        
                        workers.append({
                            "id": worker_id,
                            "status": status,
                            "last_heartbeat": last_seen.isoformat(),
                            "seconds_since_heartbeat": int(seconds_ago),
                            "hostname": heartbeat.get("hostname"),
                            "version": heartbeat.get("version"),
                            "pid": heartbeat.get("pid")
                        })
                    except (json.JSONDecodeError, ValueError) as e:
                        logger.warning(f"Invalid heartbeat data for {worker_id}: {e}")
                        
    except Exception as e:
        logger.error(f"Error getting workers: {e}")
        
    return {"workers": workers, "total": len(workers)}


@router.get("/failed_commands")
async def get_failed_commands(
    device: Optional[str] = Query(None, description="Filter by device name"),
    error_type: Optional[str] = Query(None, description="Filter by error type"),
    since: Optional[int] = Query(None, description="Unix timestamp for time range"),
    limit: int = Query(100, description="Maximum results to return"),
    redis: aioredis.Redis = Depends(get_redis_client)
) -> Dict[str, Any]:
    """Query failed commands from the Redis stream.
    
    Returns recent failed commands with filtering options.
    """
    failures = []
    
    try:
        # Read from the failed commands stream
        # Start from the beginning or from the specified timestamp
        if since:
            # Read from a specific timestamp
            stream_data = await redis.xrevrange(
                "tom:failed_commands",
                max=f"{since * 1000}-0",
                count=limit * 2  # Read extra to account for filtering
            )
        else:
            # Read most recent entries
            stream_data = await redis.xrevrange(
                "tom:failed_commands",
                count=limit * 2  # Read extra to account for filtering
            )
        
        for entry_id, data in stream_data:
            # Convert bytes to strings if needed
            entry = {}
            for k, v in data.items():
                k_str = k.decode() if isinstance(k, bytes) else k
                v_str = v.decode() if isinstance(v, bytes) else v
                entry[k_str] = v_str
            
            # Apply filters
            if device and entry.get("device") != device:
                continue
            if error_type and entry.get("error_type") != error_type:
                continue
                
            # Parse timestamp from stream ID
            timestamp_ms = entry_id.decode() if isinstance(entry_id, bytes) else entry_id
            timestamp_ms = timestamp_ms.split("-")[0]
            timestamp = int(timestamp_ms) / 1000
            
            failures.append({
                "timestamp": datetime.fromtimestamp(timestamp).isoformat(),
                "device": entry.get("device"),
                "command": entry.get("command"),
                "error_type": entry.get("error_type"),
                "error": entry.get("error"),
                "job_id": entry.get("job_id"),
                "worker": entry.get("worker_id"),
                "credential_id": entry.get("credential_id"),
                "attempts": int(entry.get("attempts", 1))
            })
            
            if len(failures) >= limit:
                break
                
    except Exception as e:
        logger.error(f"Error getting failed commands: {e}")
        
    return {"failures": failures, "total": len(failures)}


@router.get("/device_stats/{device_name}")
async def get_device_stats(
    device_name: str,
    redis: aioredis.Redis = Depends(get_redis_client)
) -> Dict[str, Any]:
    """Get statistics for a specific device.
    
    Returns success/failure counts and error breakdown.
    """
    stats = {
        "device": device_name,
        "stats": {},
        "recent_failures": []
    }
    
    try:
        # Get device stats from Redis
        stats_key = f"tom:stats:device:{device_name}"
        device_stats = await redis.hgetall(stats_key)  # type: ignore
        
        if device_stats:
            # Convert bytes and calculate rates
            total_complete = 0
            total_failed = 0
            error_breakdown = {}
            
            for k, v in device_stats.items():
                k_str = k.decode() if isinstance(k, bytes) else k
                v_int = int(v.decode() if isinstance(v, bytes) else v)
                
                if k_str == "complete":
                    total_complete = v_int
                elif k_str == "failed":
                    total_failed = v_int
                elif k_str.endswith("_failed"):
                    error_type = k_str.replace("_failed", "")
                    error_breakdown[error_type] = v_int
            
            total = total_complete + total_failed
            failure_rate = (total_failed / total * 100) if total > 0 else 0
            
            stats["stats"] = {
                "total_success": total_complete,
                "total_failed": total_failed,
                "total": total,
                "failure_rate": round(failure_rate, 2),
                "error_breakdown": error_breakdown
            }
        
        # Get recent failures for this device
        stream_data = await redis.xrevrange(
            "tom:failed_commands",
            count=10
        )
        
        for entry_id, data in stream_data:
            # Convert bytes to strings
            entry = {}
            for k, v in data.items():
                k_str = k.decode() if isinstance(k, bytes) else k
                v_str = v.decode() if isinstance(v, bytes) else v
                entry[k_str] = v_str
            
            if entry.get("device") == device_name:
                # Parse timestamp
                timestamp_ms = entry_id.decode() if isinstance(entry_id, bytes) else entry_id
                timestamp_ms = timestamp_ms.split("-")[0]
                timestamp = int(timestamp_ms) / 1000
                
                stats["recent_failures"].append({
                    "timestamp": datetime.fromtimestamp(timestamp).isoformat(),
                    "command": entry.get("command"),
                    "error_type": entry.get("error_type"),
                    "error": entry.get("error", "")[:200]  # Truncate long errors
                })
                
    except Exception as e:
        logger.error(f"Error getting device stats: {e}")
        
    return stats


@router.get("/stats/summary")
async def get_stats_summary(
    redis: aioredis.Redis = Depends(get_redis_client)
) -> Dict[str, Any]:
    """Get overall system statistics summary.
    
    Returns global stats, worker breakdown, and top devices.
    """
    summary = {
        "global": {},
        "workers": [],
        "top_devices": []
    }
    
    try:
        # Get global stats
        global_stats = await redis.hgetall("tom:stats:global")  # type: ignore
        if global_stats:
            total_complete = 0
            total_failed = 0
            
            for k, v in global_stats.items():
                k_str = k.decode() if isinstance(k, bytes) else k
                v_int = int(v.decode() if isinstance(v, bytes) else v)
                
                if k_str == "complete":
                    total_complete = v_int
                elif k_str == "failed":
                    total_failed = v_int
            
            total = total_complete + total_failed
            success_rate = (total_complete / total * 100) if total > 0 else 0
            
            summary["global"] = {
                "total_jobs": total,
                "successful": total_complete,
                "failed": total_failed,
                "success_rate": round(success_rate, 2)
            }
        
        # Get worker stats
        async for key in redis.scan_iter(match="tom:stats:worker:*"):
            key_str = key.decode() if isinstance(key, bytes) else key
            parts = key_str.split(":")
            if len(parts) >= 4:
                worker_id = parts[3]
                worker_stats = await redis.hgetall(key)  # type: ignore
                
                if worker_stats:
                    complete = 0
                    failed = 0
                    
                    for k, v in worker_stats.items():
                        k_str = k.decode() if isinstance(k, bytes) else k
                        v_int = int(v.decode() if isinstance(v, bytes) else v)
                        
                        if k_str == "complete":
                            complete = v_int
                        elif k_str == "failed":
                            failed = v_int
                    
                    summary["workers"].append({
                        "id": worker_id,
                        "complete": complete,
                        "failed": failed,
                        "total": complete + failed
                    })
        
        # Get top devices by job count
        device_totals = []
        async for key in redis.scan_iter(match="tom:stats:device:*"):
            key_str = key.decode() if isinstance(key, bytes) else key
            parts = key_str.split(":")
            if len(parts) >= 4:
                device_name = parts[3]
                device_stats = await redis.hgetall(key)  # type: ignore
                
                if device_stats:
                    complete = 0
                    failed = 0
                    
                    for k, v in device_stats.items():
                        k_str = k.decode() if isinstance(k, bytes) else k
                        v_int = int(v.decode() if isinstance(v, bytes) else v)
                        
                        if k_str == "complete":
                            complete = v_int
                        elif k_str == "failed":
                            failed = v_int
                    
                    device_totals.append({
                        "device": device_name,
                        "complete": complete,
                        "failed": failed,
                        "total": complete + failed
                    })
        
        # Sort by total and take top 10
        device_totals.sort(key=lambda x: x["total"], reverse=True)
        summary["top_devices"] = device_totals[:10]
        
    except Exception as e:
        logger.error(f"Error getting stats summary: {e}")
        
    return summary