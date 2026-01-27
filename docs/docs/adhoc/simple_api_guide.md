# Simple API Guide

This document explains the main Tom controller HTTP API flows: starting sync/async jobs against inventory devices, controlling caching, and selecting parsing templates. It covers the primary, common paths (not every edge case).

## Overview
- Tom exposes HTTP endpoints to run commands against inventory devices (synchronously or asynchronously), control caching, and choose parsing templates.
- Authentication: API key header or JWT (configurable).

## Authentication
- Modes: `none`, `api_key`, `jwt`, `hybrid` (configurable in settings).
- API key: send a header (default `X-API-Key`) with a configured API key (settings `api_keys` use `"key:user"` entries).
  - Example: `curl -H "X-API-Key: mykey" http://tom:8020/api/...`
- JWT: send a bearer token in `Authorization: Bearer <token>`; Tom validates tokens against configured OIDC providers.

## Response Types

### JobResponse (Default)
Jobs use the `JobResponse` structure with fields: `job_id`, `status` (`NEW|QUEUED|ACTIVE|COMPLETE|FAILED|ABORTED`), `result`, `metadata`, `attempts`, `error`.

Command outputs are in `result["data"]` and cache info in `result["meta"]["cache"]`.

```json
{
  "job_id": "abc123",
  "status": "COMPLETE",
  "result": {
    "data": {"show version": "..."},
    "meta": {"cache": {...}}
  },
  "attempts": 1,
  "error": null
}
```

### Raw Output Mode
Set `raw_output=true` to opt out of the JobResponse envelope and get plain text (`text/plain`). Useful for piping output to other tools.

**Requires:** `wait=true`

**Error responses:** Returns appropriate HTTP status codes (404, 500, 502) with plain text error messages.

## Start a job (device via inventory)

### Single command (sync or async)
- Endpoint: `POST /api/device/{device_name}/send_command`

**Request body fields:**
- `command` (required): Command to execute
- `wait` (bool): `true` = synchronous (wait for job completion), `false` = async (returns job info)
- `raw_output` (bool): Return plain text output (requires `wait=true`)
- `use_cache` (bool): Allow use of cached results (works with `wait=true`)
- `cache_ttl` (int seconds): TTL for cache
- `cache_refresh` (bool): Force refresh of cache
- `parse` (bool): Parse output (only meaningful with `wait=true`; for async parsing, use `GET /api/job/{job_id}?parse=true`)
- `parser` (`textfsm` or `ttp`): Parser to use
- `template` (string): Template filename to use for parsing
- `include_raw` (bool): Include raw output along with parsed data
- `username`/`password`: Optional inline credential override

**Behavior:**
- If `wait=true`, API returns parsed or raw output depending on parameters.
- If `wait=false`, API returns a job object with `job_id` to poll.
- If `raw_output=true`, returns plain text instead of JSON.

### Multiple commands
- Endpoint: `POST /api/device/{device_name}/send_commands`

Two modes:
1. **Simple mode**: Array of command strings with global settings
2. **Advanced mode**: Per-command configuration with individual parse settings

#### Simple mode
```json
{
  "commands": ["show ip int brief", "show version"],
  "wait": true,
  "parse": true,
  "parser": "textfsm"
}
```

#### Advanced mode (per-command control)
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

#### Raw output mode
```json
{
  "commands": ["show version", "show ip int brief"],
  "wait": true,
  "raw_output": true
}
```

Returns plain text with commands separated:
```
### show version ###
<output>

### show ip int brief ###
<output>
```

#### Request body fields
- `commands`: Array of strings or CommandSpec objects
- `wait` (bool): Wait for job completion
- `raw_output` (bool): Return plain text output (requires `wait=true`)
- `timeout` (int): Timeout in seconds when wait=true
- `parse` (bool): Default parse setting for commands
- `parser` ("textfsm" or "ttp"): Default parser
- `include_raw` (bool): Default include raw with parsed
- `use_cache` (bool): Use cache for results (default: true for multi-command)
- `cache_refresh` (bool): Force cache refresh
- `cache_ttl` (int): Cache TTL in seconds
- `retries` (int): Number of retries on transient failures (default: 3)
- `max_queue_wait` (int): Max seconds to wait for device semaphore (default: 300)
- `username`/`password`: Optional credential override

#### CommandSpec fields (for advanced mode)
- `command` (string): The command to execute
- `parse` (bool): Whether to parse this command
- `parser` ("textfsm" or "ttp"): Parser for this command
- `template` (string): Template file for this command
- `include_raw` (bool): Include raw with parsed for this command

### Raw/Direct host endpoints
- `POST /api/raw/send_netmiko_command`
- `POST /api/raw/send_scrapli_command`

These endpoints bypass inventory lookup and connect directly to hosts. They support the same features as inventory-based endpoints.

**Required fields:**
- `host`: Device hostname or IP
- `device_type`: Device type (e.g., cisco_ios, arista_eos)
- `command`: Command to execute
- Credentials: Either `credential_id` OR `username`+`password`

**Optional fields:**
- `port` (default: 22): SSH port
- `wait` (default: false): Wait for job completion
- `timeout` (default: 10): Timeout in seconds
- `raw_output` (default: false): Return plain text output
- `parse` (default: false): Parse output using TextFSM/TTP
- `parser` (default: "textfsm"): Parser to use ("textfsm" or "ttp")
- `template`: Explicit template name for parsing
- `include_raw` (default: false): Include raw output with parsed result
- `use_cache` (default: false): Use cache for command results
- `cache_ttl`: Cache TTL in seconds
- `cache_refresh` (default: false): Force refresh cache

**Example with parsing:**
```bash
curl -X POST -H "X-API-Key: MYKEY" -H "Content-Type: application/json" \
  -d '{
    "host": "192.168.1.1",
    "device_type": "cisco_ios",
    "command": "show ip int brief",
    "credential_id": "default",
    "wait": true,
    "parse": true,
    "parser": "textfsm"
  }' \
  "http://tom:8020/api/raw/send_netmiko_command"
```

## Async job control / status
- Check job status / results: `GET /api/job/{job_id}`
- Optional parse query params (`parse`, `parser`, `template`, `include_raw`) let you request parsing for a completed async job.
- `JobResponse` provides helpers: `command_data` (command -> output) and `cache_metadata`.

## Inventory
- Get device config: `GET /api/inventory/{device_name}` -> returns `DeviceConfig` (host, adapter, adapter_driver, credential_id, port, etc.)
- Export inventory: `GET /api/inventory/export` (DeviceConfig map) and `GET /api/inventory/export/raw` (raw nodes)
  - Supports filtering (see "Inventory filtering" below)
- List available fields: `GET /api/inventory/fields` - returns filterable fields for current inventory source
- List named filters: `GET /api/inventory/filters` - returns available predefined filter names

### Inventory filtering
Tom supports two filtering modes for inventory export endpoints:

#### 1. Named Filters (Predefined)
Use the `filter_name` query parameter with predefined filter names:
- `switches` - Common switch types (Dell, Arista, Cisco)
- `routers` - Common router types (Cisco ASR, Juniper MX)
- `arista_exclusion` - Arista devices excluding specific models
- `iosxe` - Cisco IOS-XE devices (excludes Nexus, ASA, ISE, ONS)
- `ospf_crawler_filter` - Devices used by ospf_crawler (Cisco ASR, 29xx, Juniper MX104)

**Examples:**
```bash
curl -H "X-API-Key: MYKEY" "http://tom:8020/api/inventory/export?filter_name=switches"
curl -H "X-API-Key: MYKEY" "http://tom:8020/api/inventory/export/raw?filter_name=routers"
```

#### 2. Inline Filters (Flexible)
Use query parameters matching field names with regex patterns. Available fields vary by inventory source:

**SolarWinds fields:** `NodeID`, `IPAddress`, `Uri`, `Caption`, `Description`, `Status`, `Vendor`, `DetailsUrl`
**YAML fields:** `Caption`, `host`, `adapter`, `adapter_driver`, `credential_id`, `port`

**Examples:**
```bash
# Filter by vendor and description
curl "http://tom:8020/api/inventory/export?Vendor=cisco&Description=asr.*"

# Filter by hostname pattern
curl "http://tom:8020/api/inventory/export?Caption=^router.*"

# Multiple field filters (all must match)
curl "http://tom:8020/api/inventory/export?Vendor=arista&Description=DCS-7.*&Caption=.*-sw01"
```

**Notes:**
- If `filter_name` is provided, it takes precedence over inline filters
- All filter patterns are case-insensitive regex patterns
- Multiple field filters use logical AND (all must match)
- Use `GET /api/inventory/fields` to discover available fields for your inventory source
- Invalid regex patterns will return an error

## Templates & parsing
- List TextFSM templates: `GET /api/templates/textfsm`
- Find matching template: `GET /api/templates/match`
  - Query params: `command` (required), plus either `device_type` or `device` (inventory lookup), and optionally `parser` (`textfsm` or `ttp`).
  - Returns which template(s) would be used to parse that command, including template name, source (`custom` or `ntc-templates`), and parser type.
  - Example: `GET /api/templates/match?device_type=cisco_ios&command=show+version`
  - Example with inventory device: `GET /api/templates/match?device=router1&command=show+ip+int+brief`
- Test parsing without executing commands: `POST /api/parse/test`
  - Submit raw text and query params `parser`, `template`, `device_type`, `command`, `include_raw`.

## Caching
- Controlled per-request (device endpoints) with request body fields:
  - `use_cache=true` - allow returning cached result (effective with `wait=true`)
  - `cache_ttl=<seconds>` - TTL for the cache entry
  - `cache_refresh=true` - force bypass/update cache
- Cache metadata is included in the `result.meta.cache` field of JobResponse.

## Parsing selection
- Parsers supported: `textfsm` (default) and `ttp`.
- Use `template=<template_filename>` to pick a template (e.g., `cisco_ios_show_ip_int_brief.textfsm`).
- `include_raw=true` returns raw text alongside parsed output.
- For multiple commands: Can specify different parsers/templates per command (see "Multiple commands" section above).

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

## Credentials
- `GET /api/credentials` - list available credential IDs from the configured credential store (optional `timeout` param)

## Monitoring
- `GET /api/monitoring/workers` - worker status based on heartbeats
- `GET /api/monitoring/failed_commands` - failed command history (optional filters: `device`, `error_type`, `since`, `limit`)
- `GET /api/monitoring/device_stats/{device_name}` - success/failure counts for a specific device
- `GET /api/monitoring/stats/summary` - global stats, worker breakdown, top devices

## Metrics
- `GET /metrics` - Prometheus metrics endpoint (unauthenticated, outside `/api/` prefix)

## Convenience / debug endpoints
- `GET /api/auth/debug` - shows resolved auth method and token claims (requires auth)
- OAuth test/development endpoints (may be disabled or restricted to localhost):
  - `POST /api/oauth/token` - exchange test auth code for tokens
  - `GET /api/oauth/config` - config for test frontend
  - `GET /api/userinfo?access_token=...` - fetch userinfo from provider

## Examples

### Async job (POST, API key header)
```bash
curl -X POST -H "X-API-Key: MYKEY" -H "Content-Type: application/json" \
  -d '{"command": "show ip int brief"}' \
  "http://tom:8020/api/device/router1/send_command"
```
Response contains `job_id`; poll `GET /api/job/{job_id}`.

### Sync job, parse with TextFSM
```bash
curl -X POST -H "X-API-Key: MYKEY" -H "Content-Type: application/json" \
  -d '{
    "command": "show ip int brief",
    "wait": true,
    "parse": true,
    "parser": "textfsm",
    "template": "cisco_ios_show_ip_int_brief.textfsm"
  }' \
  "http://tom:8020/api/device/router1/send_command"
```

### Raw output mode (plain text)
```bash
curl -X POST -H "X-API-Key: MYKEY" -H "Content-Type: application/json" \
  -d '{
    "command": "show version",
    "wait": true,
    "raw_output": true
  }' \
  "http://tom:8020/api/device/router1/send_command"
```

### Force cache refresh and set TTL
```bash
curl -X POST -H "X-API-Key: MYKEY" -H "Content-Type: application/json" \
  -d '{
    "command": "show version",
    "wait": true,
    "use_cache": true,
    "cache_refresh": true,
    "cache_ttl": 300
  }' \
  "http://tom:8020/api/device/router1/send_command"
```

### Multiple commands (simple mode)
```bash
curl -H "X-API-Key: MYKEY" -H "Content-Type: application/json" \
  -d '{
    "commands": ["show ip int brief", "show version"],
    "wait": true,
    "parse": true
  }' \
  "http://tom:8020/api/device/router1/send_commands"
```

### Multiple commands (per-command parsing)
```bash
curl -H "X-API-Key: MYKEY" -H "Content-Type: application/json" \
  -d '{
    "commands": [
      {"command": "show version", "parse": true, "template": "custom_version.textfsm"},
      {"command": "show ip int brief", "parse": true},
      {"command": "show running-config", "parse": false}
    ],
    "wait": true
  }' \
  "http://tom:8020/api/device/router1/send_commands"
```

### Multiple commands (raw output)
```bash
curl -H "X-API-Key: MYKEY" -H "Content-Type: application/json" \
  -d '{
    "commands": ["show version", "show ip int brief"],
    "wait": true,
    "raw_output": true
  }' \
  "http://tom:8020/api/device/router1/send_commands"
```

## Notes / assumptions
- Inventory devices usually provide stored `credential_id` entries that Tom uses automatically; per-request overrides are available with `username`+`password`.
- Some debug and OAuth test endpoints are intended for local/dev use and may be restricted or disabled by configuration.
- This guide shows the common flows; for adapter-specific behavior, advanced options, or edge cases, see the controller code and config (`services/controller/src/tom_controller/api/`).
