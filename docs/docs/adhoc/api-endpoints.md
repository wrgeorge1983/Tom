# Tom Smykowski API Endpoints

This document describes the available API endpoints for the Tom Smykowski network automation broker service.

## Base URL

All endpoints are prefixed with `/api/`

## Authentication

Authentication modes (configure via `tom_config.yaml` or env):
- `none` (default): No authentication required
- `api_key`: Requires API key in header (default `X-API-Key`)
- `jwt`: Bearer JWT via OAuth/OIDC providers
- `hybrid`: Accept either API key or JWT

When using `jwt`/`hybrid`, authorization policy applies (if configured): precedence `allowed_users` -> `allowed_domains` -> `allowed_user_regex`. Any match grants access. See [OAuth Implementation](oauth-implementation.md) for details.

## Response Types

### JobResponse (Default)

All command execution endpoints return a consistent `JobResponse` envelope:

```json
{
  "job_id": "abc123",
  "status": "COMPLETE",
  "result": {
    "data": {
      "show version": "..."
    },
    "meta": {
      "cache": {...}
    }
  },
  "attempts": 1,
  "error": null
}
```

### Raw Output Mode

For endpoints that support it, setting `raw_output=true` opts out of the JobResponse envelope and returns plain text (`text/plain`). This is useful for network engineers who want to pipe output directly to other tools.

**Requires:** `wait=true`

**Error responses in raw output mode:**
- 404: Device/resource not found
- 500: Queue/adapter errors
- 502: Device command execution failed

## Endpoints

### Device Command Execution

#### Single Command

```
POST /api/device/{device_name}/send_command
```

Send a single command to a device from inventory.

**Request Body:**
```json
{
  "command": "show version",
  "wait": false,
  "raw_output": false,
  "timeout": 10,
  "use_cache": false,
  "cache_ttl": 300,
  "cache_refresh": false,
  "parse": false,
  "parser": "textfsm",
  "template": "cisco_ios_show_version.textfsm",
  "include_raw": false,
  "username": "optional",
  "password": "optional"
}
```

**Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `command` | string | required | Command to execute |
| `wait` | bool | false | Wait for job completion |
| `raw_output` | bool | false | Return plain text output (requires wait=true) |
| `timeout` | int | 10 | Timeout in seconds |
| `use_cache` | bool | false | Enable caching for this request |
| `cache_ttl` | int | null | Override default TTL in seconds |
| `cache_refresh` | bool | false | Force refresh, bypassing cache |
| `parse` | bool | false | Parse output using TextFSM/TTP |
| `parser` | string | "textfsm" | Parser to use ("textfsm" or "ttp") |
| `template` | string | null | Explicit template name for parsing |
| `include_raw` | bool | false | Include raw output with parsed result |
| `username` | string | null | Override username (requires password) |
| `password` | string | null | Override password (requires username) |

**Returns:**
- Default: `JobResponse` object
- With `raw_output=true`: Plain text device output

#### Multiple Commands

```
POST /api/device/{device_name}/send_commands
```

Send multiple commands to a device with optional per-command parsing configuration.

**Simple Mode Request:**
```json
{
  "commands": ["show version", "show ip int brief"],
  "wait": true,
  "parse": true,
  "parser": "textfsm"
}
```

**Advanced Mode Request (per-command control):**
```json
{
  "commands": [
    {
      "command": "show version",
      "parse": true,
      "template": "custom_version.textfsm"
    },
    {
      "command": "show ip int brief",
      "parse": true
    },
    {
      "command": "show running-config",
      "parse": false
    }
  ],
  "wait": true
}
```

**Raw Output Mode:**
```json
{
  "commands": ["show version", "show ip int brief"],
  "wait": true,
  "raw_output": true
}
```

Raw output for multiple commands is formatted as:
```
### show version ###
<output>

### show ip int brief ###
<output>
```

**Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `commands` | array | required | List of commands (strings or CommandSpec objects) |
| `wait` | bool | false | Wait for job completion |
| `raw_output` | bool | false | Return plain text output (requires wait=true) |
| `timeout` | int | 10 | Timeout in seconds |
| `parse` | bool | false | Default parse setting for commands |
| `parser` | string | "textfsm" | Default parser to use |
| `include_raw` | bool | false | Default include raw with parsed |
| `use_cache` | bool | true | Use cache for results |
| `cache_refresh` | bool | false | Force cache refresh |
| `cache_ttl` | int | null | Cache TTL in seconds |
| `retries` | int | 3 | Number of retries on transient failures |
| `max_queue_wait` | int | 300 | Max seconds to wait for device semaphore |
| `username` | string | null | Override credentials |
| `password` | string | null | Override credentials |

**CommandSpec Fields (for advanced mode):**
| Field | Type | Description |
|-------|------|-------------|
| `command` | string | The command to execute |
| `parse` | bool | Whether to parse this command |
| `parser` | string | Parser for this command ("textfsm" or "ttp") |
| `template` | string | Template file for this command |
| `include_raw` | bool | Include raw with parsed for this command |

**Returns:**
- Default: `JobResponse` object
- With `raw_output=true`: Plain text with all command outputs

### Raw/Direct Host Endpoints

These endpoints bypass inventory lookup and connect directly to hosts.
They support the same output modes, parsing, and caching options as the 
inventory-based endpoints.

#### Netmiko Command

```
POST /api/raw/send_netmiko_command
```

#### Scrapli Command

```
POST /api/raw/send_scrapli_command
```

**Request Body (both endpoints):**
```json
{
  "host": "192.168.1.1",
  "device_type": "cisco_ios",
  "command": "show version",
  "port": 22,
  "wait": true,
  "timeout": 10,
  "credential_id": "default",
  "raw_output": false,
  "parse": false,
  "parser": "textfsm",
  "template": null,
  "include_raw": false,
  "use_cache": false,
  "cache_ttl": null,
  "cache_refresh": false
}
```

Or with inline credentials:
```json
{
  "host": "192.168.1.1",
  "device_type": "cisco_ios",
  "command": "show version",
  "username": "admin",
  "password": "secret",
  "wait": true,
  "parse": true
}
```

**Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `host` | string | required | Device hostname or IP |
| `device_type` | string | required | Device type (e.g., cisco_ios, arista_eos) |
| `command` | string | required | Command to execute |
| `port` | int | 22 | SSH port |
| `wait` | bool | false | Wait for job completion |
| `timeout` | int | 10 | Timeout in seconds |
| `raw_output` | bool | false | Return plain text output (requires wait=true) |
| `parse` | bool | false | Parse output using TextFSM/TTP |
| `parser` | string | "textfsm" | Parser to use ("textfsm" or "ttp") |
| `template` | string | null | Explicit template name for parsing |
| `include_raw` | bool | false | Include raw output with parsed result |
| `use_cache` | bool | false | Use cache for command results |
| `cache_ttl` | int | null | Cache TTL in seconds |
| `cache_refresh` | bool | false | Force refresh cache |
| `credential_id` | string | null | Stored credential ID |
| `username` | string | null | SSH username (requires password) |
| `password` | string | null | SSH password (requires username) |

**Note:** You must provide either `credential_id` OR `username` + `password`.

**Returns:**
- Default: `JobResponse` object
- With `raw_output=true`: Plain text device output
- With `parse=true`: `JobResponse` with parsed data in result

### Job Management

#### Get Job Status

```
GET /api/job/{job_id}
```

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `parse` | bool | false | Parse output using TextFSM/TTP |
| `parser` | string | "textfsm" | Parser to use |
| `template` | string | null | Template name for parsing |
| `include_raw` | bool | false | Include raw output with parsed |

**Returns:** `JobResponse` object or null if job not found

### Inventory Management

#### Get Device Configuration

```
GET /api/inventory/{device_name}
```

**Returns:** `DeviceConfig` object
```json
{
  "adapter": "netmiko|scrapli",
  "adapter_driver": "cisco_ios",
  "adapter_options": {},
  "host": "192.168.1.1",
  "port": 22,
  "credential_id": "default"
}
```

#### Export Inventory (DeviceConfig Format)

```
GET /api/inventory/export?filter_name={filter}
```

**Parameters:**
- `filter_name` (string, optional): Filter name (see filters endpoint)

**Returns:** Dictionary of device names to `DeviceConfig` objects

#### Export Raw Inventory

```
GET /api/inventory/export/raw?filter_name={filter}
```

**Returns:** Array of raw inventory nodes (format varies by inventory source)

#### List Available Filters

```
GET /api/inventory/filters
```

**Returns:** Dictionary of filter names to descriptions

#### List Inventory Fields

```
GET /api/inventory/fields
```

**Returns:** List of filterable fields for the current inventory source

### Cache Management

#### Invalidate Device Cache

```
DELETE /api/cache/{device_name}
```

**Returns:**
```json
{
  "device": "router1",
  "deleted_count": 15,
  "message": "Invalidated 15 cache entries for router1"
}
```

#### Clear All Cache

```
DELETE /api/cache
```

**Returns:**
```json
{
  "deleted_count": 127,
  "message": "Cleared 127 cache entries"
}
```

#### List Cache Keys

```
GET /api/cache
```

**Parameters:**
- `device_name` (string, optional): Filter keys by device name

**Returns:**
```json
{
  "device_filter": "router1",
  "count": 3,
  "keys": [
    "router1:show version",
    "router1:show ip int brief"
  ]
}
```

#### Get Cache Statistics

```
GET /api/cache/stats
```

**Returns:**
```json
{
  "enabled": true,
  "total_entries": 127,
  "devices_cached": 15,
  "entries_per_device": {...},
  "default_ttl": 300,
  "max_ttl": 3600,
  "key_prefix": "tom_cache"
}
```

### Credentials

#### List Credentials

```
GET /api/credentials
```

**Parameters:**
- `timeout` (int, optional): Maximum wait time in seconds (default: 30)

**Returns:**
```json
{
  "credentials": ["default", "admin", "readonly"]
}
```

### Monitoring

#### Get Worker Status

```
GET /api/monitoring/workers
```

**Returns:** Worker status based on heartbeats

#### Get Failed Commands

```
GET /api/monitoring/failed_commands
```

**Parameters:**
- `device` (string, optional): Filter by device name
- `error_type` (string, optional): Filter by error type
- `since` (int, optional): Unix timestamp for time range start
- `limit` (int, optional): Maximum results (default: 100)

#### Get Device Statistics

```
GET /api/monitoring/device_stats/{device_name}
```

**Returns:** Success/failure counts and error breakdown for a specific device

#### Get Summary Statistics

```
GET /api/monitoring/stats/summary
```

**Returns:** Global stats, worker breakdown, and top devices

### Templates & Parsing

#### List TextFSM Templates

```
GET /api/templates/textfsm
```

**Returns:** List of available TextFSM template names

#### Find Matching Template

```
GET /api/templates/match
```

**Parameters:**
- `command` (string, required): Command to find template for
- `device_type` (string): Device type/platform (required if `device` not specified)
- `device` (string): Inventory device name (if provided, device_type is looked up)
- `parser` (string, optional): Parser type ("textfsm" or "ttp")

**Returns:**
```json
{
  "device_type": "cisco_ios",
  "command": "show version",
  "matches": [
    {
      "template_name": "cisco_ios_show_version.textfsm",
      "source": "ntc-templates",
      "parser": "textfsm"
    }
  ]
}
```

#### Test Parsing

```
POST /api/parse/test
```

Test parsing without executing commands.

**Parameters:**
- `parser` (string): Parser to use ("textfsm" or "ttp")
- `template` (string): Template filename
- `device_type` (string, optional): Device type for template auto-discovery
- `command` (string, optional): Command for template auto-discovery
- `include_raw` (bool, optional): Include raw output in response

**Request Body:** Raw text output to parse

**Returns:** Parsed result

### Metrics

#### Prometheus Metrics

```
GET /metrics
```

**Note:** This endpoint is outside the `/api/` prefix and is unauthenticated.

**Returns:** Prometheus-format metrics

## Error Responses

All errors return JSON with consistent structure:

```json
{
  "error": "Error Type",
  "detail": "Detailed error message"
}
```

| Status Code | Error Type | Description |
|-------------|------------|-------------|
| 400 | Bad Request | Validation error |
| 401 | Unauthorized | Authentication required |
| 403 | Forbidden | Authorization failed |
| 404 | Not Found | Resource not found |
| 404 | Template Not Found | Parsing template not found |
| 422 | Parsing Failed | Output parsing failed |
| 500 | Internal Server Error | Server error |

**Note:** When using `raw_output=true`, errors return plain text with appropriate HTTP status codes instead of JSON.

## Data Types

### JobResponse

```json
{
  "job_id": "job-uuid",
  "status": "NEW|QUEUED|ACTIVE|COMPLETE|FAILED|ABORTED|ABORTING",
  "result": {
    "data": {"command": "output"},
    "meta": {"cache": {...}}
  },
  "attempts": 1,
  "error": "error message (when failed)"
}
```

### DeviceConfig

```json
{
  "adapter": "netmiko|scrapli",
  "adapter_driver": "cisco_ios",
  "adapter_options": {},
  "host": "192.168.1.1",
  "port": 22,
  "credential_id": "default"
}
```

## Configuration

Configuration is managed via `tom_config.yaml` or environment variables with `TOM_` prefix.

Key settings:
- `inventory_type`: "yaml", "netbox", "nautobot", or "solarwinds"
- `auth_mode`: "none", "api_key", "jwt", or "hybrid"
- `cache_enabled`: Enable/disable caching (default: true)
- `cache_default_ttl`: Default cache TTL in seconds (default: 300)
- `cache_max_ttl`: Maximum allowed TTL in seconds (default: 3600)
