# Tom Monitoring Metrics

Tom exposes Prometheus-compatible metrics at `/api/metrics` for monitoring job execution, worker health, and system performance.

## Overview

Metrics are collected in Redis by workers and aggregated by the controller on each Prometheus scrape. The system uses a stateless collection model with 1-hour TTL on stats.

## Available Metrics

### Job Metrics

#### `tom_jobs_total` (counter)
Total number of jobs processed by the system.

**Type:** Counter  
**Labels:**
- `worker` - Worker ID (e.g., `worker-abc123` or `all` for aggregated)
- `device` - Device hostname/IP (e.g., `192.168.1.1` or `all` for aggregated)
- `status` - Job outcome: `success` or `failed`
- `error_type` - Error classification: `none`, `auth`, `timeout`, `network`, `gating`, `other`, or `all` for aggregated

**Example:**
```
tom_jobs_total{worker="worker-abc123",device="192.168.1.1",status="success",error_type="none"} 42
tom_jobs_total{worker="all",device="all",status="failed",error_type="auth"} 5
```

**Use Cases:**
- Calculate success/failure rates
- Identify problematic devices
- Track authentication issues
- Monitor per-worker performance

**Common Queries:**
```promql
# Overall success rate
sum(rate(tom_jobs_total{status="success"}[5m])) / sum(rate(tom_jobs_total[5m]))

# Failed jobs by error type
sum by (error_type) (rate(tom_jobs_total{status="failed"}[5m]))

# Jobs per worker
sum by (worker) (rate(tom_jobs_total[5m]))

# Device-specific failure rate
sum by (device) (rate(tom_jobs_total{status="failed"}[5m]))
```

### Worker Metrics

#### `tom_workers_active` (gauge)
Number of workers that have sent a heartbeat in the last 60 seconds.

**Type:** Gauge  
**Labels:** None

**Example:**
```
tom_workers_active 3.0
```

**Use Cases:**
- Monitor worker availability
- Detect worker crashes or restarts
- Capacity planning

#### `tom_worker_last_heartbeat` (gauge)
Unix timestamp (seconds since epoch) of the last heartbeat from each worker.

**Type:** Gauge  
**Labels:**
- `worker` - Worker ID

**Example:**
```
tom_worker_last_heartbeat{worker="worker-abc123"} 1763042861.073
```

**Use Cases:**
- Detect stale/unresponsive workers
- Worker health monitoring
- Debug worker restart patterns

**Common Queries:**
```promql
# Time since last heartbeat for each worker
time() - tom_worker_last_heartbeat

# Workers that haven't reported in 2 minutes
time() - tom_worker_last_heartbeat > 120
```

### Queue Metrics

#### `tom_queue_depth` (gauge)
Number of jobs waiting to be processed in each queue.

**Type:** Gauge  
**Labels:**
- `queue` - Queue name (typically `default`)

**Example:**
```
tom_queue_depth{queue="default"} 42.0
```

**Use Cases:**
- Monitor queue backlog
- Detect processing bottlenecks
- Capacity planning
- Alert on stuck queues

**Common Queries:**
```promql
# Queue backlog
tom_queue_depth

# Queue growing over time (potential stuck queue)
deriv(tom_queue_depth[5m]) > 0
```

### Device Semaphore Metrics

#### `tom_device_semaphore_leases` (gauge)
Number of active semaphore leases per device. Tom uses device-level semaphores to prevent concurrent connections to the same device.

**Type:** Gauge  
**Labels:**
- `device` - Device hostname/IP

**Example:**
```
tom_device_semaphore_leases{device="192.168.1.1"} 1.0
tom_device_semaphore_leases{device="192.168.1.2"} 0.0
```

**Use Cases:**
- Verify single-connection-per-device enforcement
- Debug device busy/gating issues
- Identify devices under heavy load

**Common Queries:**
```promql
# Devices currently being accessed
tom_device_semaphore_leases > 0

# Total active device connections
sum(tom_device_semaphore_leases)
```

## Error Classification

Jobs that fail are automatically classified by error type to help identify patterns:

| Error Type | Description | Common Causes |
|------------|-------------|---------------|
| `auth` | Authentication failures | Wrong credentials, account locked, SSH key issues |
| `timeout` | Job execution timeout | SAQ job timeout exceeded, slow network, long-running commands |
| `network` | Network connectivity issues | Device unreachable, DNS failure, routing problems |
| `gating` | Device busy/semaphore | Device already has an active connection, lease contention |
| `other` | Uncategorized errors | Various application errors, parsing failures, etc. |
| `none` | No error (success) | Job completed successfully |

## Data Retention

- **Metrics in Prometheus:** Configurable (default: 15 days)
- **Stats in Redis:** 1 hour TTL
- **Failed commands stream:** Last 1000 failures (auto-trimmed)
- **Metrics time-series stream:** Last 10,000 events

## Accessing Metrics

### Prometheus Scraping
Add to `prometheus.yml`:
```yaml
scrape_configs:
  - job_name: 'tom-controller'
    static_configs:
      - targets: ['controller:8000']
    metrics_path: '/api/metrics'
    scrape_interval: 30s
```

### Direct HTTP Access
```bash
curl http://localhost:8000/api/metrics
```

### Monitoring API Endpoints

In addition to Prometheus metrics, Tom provides REST API endpoints for detailed monitoring data:

- `GET /api/monitoring/workers` - List active workers with health status
- `GET /api/monitoring/stats/summary` - Aggregated statistics summary
- `GET /api/monitoring/failed_commands` - Recent failed job details
- `GET /api/monitoring/device_stats/{device}` - Per-device statistics

See [API documentation](./api-endpoints.md) for details.

## Grafana Dashboard

Tom includes a pre-configured Grafana dashboard (`monitoring/tom-dashboard.json`) with panels for:

- Job success/failure rates over time
- Active workers count
- Queue depth trends
- Error type breakdown
- Per-device success rates
- Worker health status

Import the dashboard or use the Docker Compose setup which auto-provisions it at http://localhost:3000 (admin/admin).
