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

## Job model
- Jobs use the `JobResponse` structure with fields: `job_id`, `status` (`NEW|QUEUED|ACTIVE|COMPLETE|FAILED|ABORTED`), `result`, `metadata`, `attempts`, `error`.
- Command outputs are typically in `result["data"]` and cache info in `result["meta"]["cache"]`.

## Start a job (device via inventory)

### Single command (sync or async)
- Endpoint: `GET /api/device/{device_name}/send_command`
- Important query params:
  - `command` (required)
  - `wait` (bool) — `true` = synchronous (wait for job completion), `false` = async (returns job info)
  - `use_cache` (bool) — allow use of cached results (works with `wait=true`)
  - `cache_ttl` (int seconds) — TTL for cache (works with `wait=true`)
  - `cache_refresh` (bool) — force refresh of cache (works with `wait=true`)
  - `parse` (bool) — parse output (only meaningful with `wait=true`; for async parsing, use `GET /api/job/{job_id}?parse=true`)
  - `parser` (`textfsm` or `ttp`) — parser to use
  - `template` (string) — template filename to use for parsing
  - `include_raw` (bool) — include raw output along with parsed data
  - `username`/`password` — optional inline credential override (otherwise uses stored `credential_id` from inventory)
- Behavior:
  - If `wait=true`, API returns parsed or raw output depending on parameters.
  - If `wait=false`, API returns a job object with `job_id` to poll.

### Multiple commands
- Endpoint: `POST /api/device/{device_name}/send_commands`
- Body: JSON object with command configuration
- Two modes:
  1. **Simple mode**: Array of command strings with global settings
  2. **Advanced mode**: Per-command configuration with individual parse settings
  
#### Simple mode
Body with array of commands and global defaults:
```json
{
  "commands": ["show ip int brief", "show version"],
  "wait": true,
  "parse": true,
  "parser": "textfsm"
}
```

#### Advanced mode (per-command control)
Body with individual command specifications:
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

#### Request body fields
- `commands`: Array of strings or CommandSpec objects
- `wait` (bool): Wait for job completion
- `timeout` (int): Timeout in seconds when wait=true
- `parse` (bool): Default parse setting for commands
- `parser` ("textfsm" or "ttp"): Default parser
- `include_raw` (bool): Default include raw with parsed
- `use_cache` (bool): Use cache for results
- `cache_refresh` (bool): Force cache refresh
- `cache_ttl` (int): Cache TTL in seconds
- `username`/`password`: Optional credential override

#### CommandSpec fields (for advanced mode)
- `command` (string): The command to execute
- `parse` (bool): Whether to parse this command
- `parser` ("textfsm" or "ttp"): Parser for this command
- `template` (string): Template file for this command
- `include_raw` (bool): Include raw with parsed for this command

### Raw/Direct host endpoints
- `GET /api/raw/send_netmiko_command`
- `GET /api/raw/send_scrapli_command`
- Params: `host`, `device_type`, `command`, `port`, and either `credential_id` OR `username`+`password`. `wait` supported.

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
- `switches` — Common switch types (Dell, Arista, Cisco)
- `routers` — Common router types (Cisco ASR, Juniper MX)
- `arista_exclusion` — Arista devices excluding specific models
- `iosxe` — Cisco IOS‑XE devices (excludes Nexus, ASA, ISE, ONS)
- `ospf_crawler_filter` — Devices used by ospf_crawler (Cisco ASR, 29xx, Juniper MX104)

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
- Test parsing without executing commands: `POST /api/parse/test`
  - Submit raw text and query params `parser`, `template`, `device_type`, `command`, `include_raw`.

## Caching
- Controlled per-request (device endpoints) with query params:
  - `use_cache=true` — allow returning cached result (effective with `wait=true`)
  - `cache_ttl=<seconds>` — TTL for the cache entry
  - `cache_refresh=true` — force bypass/update cache
- When returning full job responses, cache metadata (if present) is attached under `_cache`.

## Parsing selection
- Parsers supported: `textfsm` (default) and `ttp`.
- Use `template=<template_filename>` to pick a template (e.g., `cisco_ios_show_ip_int_brief.textfsm`).
- `include_raw=true` returns raw text alongside parsed output.
- For multiple commands: Can specify different parsers/templates per command (see "Multiple commands" section above).

## Convenience / debug endpoints
- `GET /api/auth/debug` — shows resolved auth method and token claims (requires auth)
- OAuth test/development endpoints (may be disabled or restricted to localhost):
  - `POST /api/oauth/token` — exchange test auth code for tokens
  - `GET /api/oauth/config` — config for test frontend
  - `GET /api/userinfo?access_token=...` — fetch userinfo from provider

## Examples
- Async job (API key header):
  - `curl -H "X-API-Key: MYKEY" "http://tom:8020/api/device/router1/send_command?command=show%20ip%20int%20brief"`
  - Response contains `job_id`; poll `GET /api/job/{job_id}`.

- Sync job, parse with TextFSM and template:
  - `curl -H "X-API-Key: MYKEY" "http://tom:8020/api/device/router1/send_command?command=show%20ip%20int%20brief&wait=true&parse=true&parser=textfsm&template=cisco_ios_show_ip_int_brief.textfsm"`

- Force cache refresh and set TTL:
  - `.../send_command?command=...&wait=true&use_cache=true&cache_refresh=true&cache_ttl=300`

- Multiple commands (simple mode):
  ```bash
  curl -H "X-API-Key: MYKEY" -H "Content-Type: application/json" \
    -d '{
      "commands": ["show ip int brief", "show version"],
      "wait": true,
      "parse": true
    }' \
    "http://tom:8020/api/device/router1/send_commands"
  ```

- Multiple commands (per-command parsing):
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

## Notes / assumptions
- Inventory devices usually provide stored `credential_id` entries that Tom uses automatically; per-request overrides are available with `username`+`password`.
- Some debug and OAuth test endpoints are intended for local/dev use and may be restricted or disabled by configuration.
- This guide shows the common flows; for adapter-specific behavior, advanced options, or edge cases, see the controller code and config (`services/controller/src/tom_controller/api/api.py` and `services/controller/src/tom_controller/config.py`).
