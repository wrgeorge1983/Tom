"""Prometheus metrics exporter for Tom Controller."""

import logging
import re
from typing import Optional

import redis.asyncio as aioredis
from prometheus_client import Counter, Gauge, Histogram, CollectorRegistry, generate_latest

logger = logging.getLogger(__name__)


class MetricsExporter:
    """Stateless metrics exporter that collects from Redis on each scrape."""
    
    def __init__(self, redis_client: aioredis.Redis):
        """Initialize the metrics exporter.
        
        Args:
            redis_client: Redis client for accessing stats
        """
        self.redis = redis_client
        
    async def generate_metrics(self) -> bytes:
        """Generate Prometheus metrics by scanning Redis.
        
        This is called on each Prometheus scrape. We create fresh metrics
        each time (stateless collection).
        
        Returns:
            Prometheus formatted metrics as bytes
        """
        # Create fresh registry for this scrape
        registry = CollectorRegistry()
        
        # Define metrics
        jobs_total = Counter(
            'tom_jobs_total',
            'Total jobs processed',
            ['worker', 'device', 'status', 'error_type'],
            registry=registry
        )
        
        workers_active = Gauge(
            'tom_workers_active',
            'Number of active workers',
            registry=registry
        )
        
        worker_heartbeat = Gauge(
            'tom_worker_last_heartbeat',
            'Unix timestamp of last worker heartbeat',
            ['worker'],
            registry=registry
        )
        
        device_semaphore_leases = Gauge(
            'tom_device_semaphore_leases',
            'Current semaphore leases per device',
            ['device'],
            registry=registry  
        )
        
        queue_depth = Gauge(
            'tom_queue_depth',
            'Jobs waiting in queue',
            ['queue'],
            registry=registry
        )
        
        # Collect worker stats
        await self._collect_worker_stats(jobs_total)
        
        # Collect device stats
        await self._collect_device_stats(jobs_total)
        
        # Count active workers from heartbeats
        active_count = await self._count_active_workers(worker_heartbeat)
        workers_active.set(active_count)
        
        # Collect device semaphore leases
        await self._collect_semaphore_leases(device_semaphore_leases)
        
        # Collect queue depth (from SAQ keys)
        await self._collect_queue_depth(queue_depth)
        
        # Generate Prometheus format
        return generate_latest(registry)
    
    async def _collect_worker_stats(self, jobs_counter: Counter):
        """Collect per-worker job stats from Redis."""
        try:
            async for key in self.redis.scan_iter(match="tom:stats:worker:*"):
                # Parse worker ID from key
                # Format: tom:stats:worker:{worker_id}
                parts = key.decode() if isinstance(key, bytes) else key
                parts = parts.split(":")
                if len(parts) >= 4:
                    worker_id = parts[3]
                    
                    # Get stats hash
                    stats = await self.redis.hgetall(key)  # type: ignore
                    
                    # Convert bytes keys/values if needed
                    stats_dict = {}
                    for k, v in stats.items():
                        k_str = k.decode() if isinstance(k, bytes) else k
                        v_str = v.decode() if isinstance(v, bytes) else v
                        stats_dict[k_str] = int(v_str)
                    
                    # Add to counter
                    if stats_dict.get('complete', 0) > 0:
                        jobs_counter.labels(
                            worker=worker_id,
                            device='all',
                            status='success',
                            error_type='none'
                        )._value.set(stats_dict['complete'])
                    
                    if stats_dict.get('failed', 0) > 0:
                        jobs_counter.labels(
                            worker=worker_id,
                            device='all',
                            status='failed',
                            error_type='all'
                        )._value.set(stats_dict['failed'])
                    
                    # Error type breakdowns
                    for error_type in ['auth', 'gating', 'timeout', 'network', 'other']:
                        key = f'{error_type}_failed'
                        if stats_dict.get(key, 0) > 0:
                            jobs_counter.labels(
                                worker=worker_id,
                                device='all',
                                status='failed',
                                error_type=error_type
                            )._value.set(stats_dict[key])
                            
        except Exception as e:
            logger.error(f"Error collecting worker stats: {e}")
    
    async def _collect_device_stats(self, jobs_counter: Counter):
        """Collect per-device job stats from Redis."""
        try:
            async for key in self.redis.scan_iter(match="tom:stats:device:*"):
                # Parse device name from key
                # Format: tom:stats:device:{device_name}
                parts = key.decode() if isinstance(key, bytes) else key
                parts = parts.split(":")
                if len(parts) >= 4:
                    device_name = parts[3]
                    
                    # Get stats hash
                    stats = await self.redis.hgetall(key)  # type: ignore
                    
                    # Convert bytes keys/values if needed
                    stats_dict = {}
                    for k, v in stats.items():
                        k_str = k.decode() if isinstance(k, bytes) else k
                        v_str = v.decode() if isinstance(v, bytes) else v
                        stats_dict[k_str] = int(v_str)
                    
                    # Add to counter
                    if stats_dict.get('complete', 0) > 0:
                        jobs_counter.labels(
                            worker='all',
                            device=device_name,
                            status='success',
                            error_type='none'
                        )._value.set(stats_dict['complete'])
                    
                    if stats_dict.get('failed', 0) > 0:
                        jobs_counter.labels(
                            worker='all',
                            device=device_name,
                            status='failed',
                            error_type='all'
                        )._value.set(stats_dict['failed'])
                    
                    # Error type breakdowns
                    for error_type in ['auth', 'gating', 'timeout', 'network', 'other']:
                        key = f'{error_type}_failed'
                        if stats_dict.get(key, 0) > 0:
                            jobs_counter.labels(
                                worker='all',
                                device=device_name,
                                status='failed',
                                error_type=error_type
                            )._value.set(stats_dict[key])
                            
        except Exception as e:
            logger.error(f"Error collecting device stats: {e}")
    
    async def _count_active_workers(self, heartbeat_gauge: Gauge) -> int:
        """Count active workers from heartbeat keys."""
        active_count = 0
        try:
            async for key in self.redis.scan_iter(match="tom:worker:heartbeat:*"):
                active_count += 1
                
                # Parse worker ID from key
                # Format: tom:worker:heartbeat:{worker_id}
                parts = key.decode() if isinstance(key, bytes) else key
                parts = parts.split(":")
                if len(parts) >= 4:
                    worker_id = parts[3]
                    
                    # Get heartbeat data
                    heartbeat_data = await self.redis.get(key)
                    if heartbeat_data:
                        import json
                        try:
                            data = json.loads(heartbeat_data)
                            timestamp = data.get('timestamp', 0)
                            heartbeat_gauge.labels(worker=worker_id).set(timestamp)
                        except json.JSONDecodeError:
                            logger.warning(f"Invalid heartbeat data for {worker_id}")
                        
        except Exception as e:
            logger.error(f"Error counting active workers: {e}")
            
        return active_count
    
    async def _collect_semaphore_leases(self, lease_gauge: Gauge):
        """Collect device semaphore lease counts."""
        try:
            # Device leases are stored as sorted sets: device_lease:{device_id}
            async for key in self.redis.scan_iter(match="device_lease:*"):
                # Parse device ID from key
                parts = key.decode() if isinstance(key, bytes) else key
                parts = parts.split(":")
                if len(parts) >= 2:
                    device_id = parts[1]
                    
                    # Count leases in sorted set
                    count = await self.redis.zcard(key)
                    lease_gauge.labels(device=device_id).set(count)
                    
        except Exception as e:
            logger.error(f"Error collecting semaphore leases: {e}")
    
    async def _collect_queue_depth(self, queue_gauge: Gauge):
        """Collect queue depth from SAQ."""
        try:
            # SAQ queues are stored with pattern saq:{queue_name}:* 
            # The main queue list is saq:{queue_name}:queue
            queue_names = ['default']  # Add more queue names if you have them
            
            for queue_name in queue_names:
                queue_key = f"saq:{queue_name}:queue"
                depth = await self.redis.llen(queue_key)  # type: ignore
                queue_gauge.labels(queue=queue_name).set(depth)
                
        except Exception as e:
            logger.error(f"Error collecting queue depth: {e}")