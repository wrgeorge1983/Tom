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
- Body: JSON array of commands, e.g. `["show ip int brief","show version"]`.
- Query params same as single-command endpoint. Note: `parse` requires `wait=true` for immediate parsing.

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
  - Optional `?filter_name=<filter>` to restrict results (see "Inventory filtering" below)
- List filters: `GET /api/inventory/filters`

### Inventory filtering
- Purpose: restrict exported inventory results to a subset of nodes using predefined, named filters.
- How it works: filters are implemented as regex-based matchers evaluated against SolarWinds node fields: `Caption` (hostname), `Vendor`, and `Description` (often contains platform/OS). A node must match all configured patterns in a filter to be included.
- Supported filter names (returned by `GET /api/inventory/filters`):
  - `switches` — Common switch types (Dell, Arista, Cisco). Matches `Vendor` and `Description` patterns for common switch models.
  - `routers` — Common router types (Cisco ASR, Juniper MX).
  - `arista_exclusion` — Matches Arista devices but excludes specific models (used to filter out certain Arista switches).
  - `iosxe` — Cisco IOS‑XE devices (excludes Nexus, ASA, ISE, ONS).
- Usage: pass `filter_name` as a query parameter to the export endpoints:
  - `GET /api/inventory/export?filter_name=switches`
  - `GET /api/inventory/export/raw?filter_name=iosxe`
- Notes:
  - Filters are case‑insensitive regular expressions applied to each node field; they are combined with logical AND (all configured patterns must match).
  - If an unknown `filter_name` is supplied the controller will raise an error (available filters can be listed via `GET /api/inventory/filters`).
  - The `FilterRegistry` lives in `services/controller/src/tom_controller/inventory/solarwinds.py` and defines both the available filter names and the underlying regexes used.
- Example: export device configs for routers only:
  - `curl -H "X-API-Key: MYKEY" "http://tom:8020/api/inventory/export?filter_name=routers"`

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

- Multiple commands (sync):
  - `curl -H "X-API-Key: MYKEY" -H "Content-Type: application/json" -d '["show ip int brief","show version"]' "http://tom:8020/api/device/router1/send_commands?wait=true&parse=true"`

## Notes / assumptions
- Inventory devices usually provide stored `credential_id` entries that Tom uses automatically; per-request overrides are available with `username`+`password`.
- Some debug and OAuth test endpoints are intended for local/dev use and may be restricted or disabled by configuration.
- This guide shows the common flows; for adapter-specific behavior, advanced options, or edge cases, see the controller code and config (`services/controller/src/tom_controller/api/api.py` and `services/controller/src/tom_controller/config.py`).
