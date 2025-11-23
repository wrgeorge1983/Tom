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

When using `jwt`/`hybrid`, authorization policy applies (if configured): precedence `allowed_users` → `allowed_domains` → `allowed_user_regex`. Any match grants access. See [OAuth Implementation](oauth-implementation.md) for details.

## Endpoints

### Device Command Execution

#### Raw Netmiko Command
```
GET /api/raw/send_netmiko_command
```

**Parameters:**
- `host` (string): Device IP address
- `device_type` (string): Netmiko device type (e.g., "cisco_ios")
- `command` (string): Command to execute
- `port` (int, optional): SSH port (default: 22)
- `wait` (bool, optional): Wait for job completion (default: false)
- Credentials (choose one):
  - `credential_id` (string): Stored credential ID
  - `username` + `password` (string): Inline SSH credentials

**Returns:** `JobResponse` object

#### Raw Scrapli Command
```
GET /api/raw/send_scrapli_command
```

**Parameters:** Same as Netmiko endpoint

**Returns:** `JobResponse` object

#### Inventory-based Single Command
```
GET /api/device/{device_name}/send_command
```

**Parameters:**
- `device_name` (string): Device name from inventory
- `command` (string): Command to execute
- `wait` (bool, optional): Wait for job completion (default: false)
- `rawOutput` (bool, optional): Return raw output (requires wait=true)
- `timeout` (int, optional): Timeout in seconds (default: 10)
- `cache` (bool, optional): Enable caching for this request (default: true)
- `cache_ttl` (int, optional): Override default TTL in seconds (capped at max_ttl)
- `cache_refresh` (bool, optional): Force refresh, bypassing cache (default: false)
- `parse` (bool, optional): Parse output using TextFSM/TTP
- `parser` (string, optional): Parser to use ("textfsm" or "ttp", default: "textfsm")
- `template` (string, optional): Explicit template name for parsing
- `include_raw` (bool, optional): Include raw output with parsed result
- Optional credential override:
  - `username` + `password` (string): Override inventory credentials

**Returns:** `JobResponse` or raw string (if rawOutput=true) or parsed result (if parse=true)

### Inventory-based Multiple Commands
```
POST /api/device/{device_name}/send_commands
```

Send multiple commands with optional per-command parsing configuration.

**Request Body:**
```json
{
  "commands": ["command1", "command2"],  // Simple mode
  // OR
  "commands": [                           // Advanced mode
    {
      "command": "show version",
      "parse": true,
      "template": "custom_version.textfsm",
      "parser": "textfsm",
      "include_raw": false
    },
    {
      "command": "show ip int brief",
      "parse": true
      // Uses defaults from request body
    }
  ],
  "wait": false,                // Wait for completion
  "timeout": 10,                // Timeout in seconds
  "parse": false,               // Default parse setting for commands
  "parser": "textfsm",          // Default parser (textfsm or ttp)
  "include_raw": false,         // Default include_raw setting
  "use_cache": true,            // Use cache
  "cache_refresh": false,       // Force cache refresh
  "cache_ttl": 300,             // Cache TTL in seconds
  "username": "optional",       // Override credentials
  "password": "optional"
}
```

**Examples:**

Simple mode (all commands use same settings):
```json
{
  "commands": ["show version", "show ip interface brief"],
  "wait": true,
  "parse": true,
  "parser": "textfsm"
}
```

Advanced mode (per-command control):
```json
{
  "commands": [
    {
      "command": "show version",
      "parse": true,
      "template": "custom_version.textfsm"
    },
    {
      "command": "show ip interface brief", 
      "parse": true
      // Auto-discovers template
    },
    {
      "command": "show running-config",
      "parse": false
      // Returns raw output only
    }
  ],
  "wait": true
}
```

Mixed mode (defaults with overrides):
```json
{
  "commands": [
    "show version",  // Uses defaults below
    {
      "command": "show interfaces",
      "parser": "ttp",  // Override to use TTP
      "template": "custom_interfaces.ttp"
    }
  ],
  "wait": true,
  "parse": true,      // Default: parse all commands
  "parser": "textfsm" // Default: use TextFSM
}
```

**Returns:** 
- If `wait=false`: `JobResponse` with job ID for async processing
- If `wait=true` and parsing enabled: Dictionary with parsed results per command
- If `wait=true` and parsing disabled: Dictionary with raw outputs per command

**Response with Cache Metadata (when cache enabled):**
```json
{
  "job_id": "...",
  "status": "COMPLETE",
  "result": {
    "data": {"show version": "..."},
    "meta": {
      "cache": {
        "cache_status": "hit",
        "commands": {
          "show version": {
            "cache_status": "hit",
            "cached_at": "2024-01-01T10:00:00Z",
            "age_seconds": 120.5
          }
        }
      }
    }
  }
}
```

### Job Management

#### Get Job Status
```
GET /api/job/{job_id}
```

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
```json
{
  "device1": {
    "adapter": "netmiko",
    "adapter_driver": "cisco_ios",
    "host": "192.168.1.1",
    "port": 22,
    "credential_id": "default"
  }
}
```

#### Export Raw Inventory
```
GET /api/inventory/export/raw?filter_name={filter}
```

**Parameters:**
- `filter_name` (string, optional): Filter name (see filters endpoint)

**Returns:** Array of raw inventory nodes (SolarWinds format for SWIS inventory)
```json
[
  {
    "NodeID": 123,
    "Caption": "device1",
    "IPAddress": "192.168.1.1",
    "Vendor": "Cisco",
    "Description": "Cisco IOS Software...",
    "Status": 1,
    "Uri": "...",
    "DetailsUrl": "..."
  }
]
```

#### List Available Filters
```
GET /api/inventory/filters
```

**Returns:** Dictionary of filter names to descriptions
```json
{
  "switches": "Common switch types (Dell, Arista, Cisco)",
  "routers": "Common router types (Cisco ASR, Juniper MX)",
  "iosxe": "Cisco IOS-XE devices (excludes Nexus and ASA)",
  "arista_exclusion": "Arista devices excluding specific models"
}
```

### Cache Management

#### Invalidate Device Cache
```
DELETE /api/cache/{device_name}
```

**Parameters:**
- `device_name` (string): Device name to invalidate cache for

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
    "router1:show ip int brief",
    "router1:show interfaces"
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
  "entries_per_device": {
    "router1": 25,
    "router2": 18,
    "switch1": 42
  },
  "default_ttl": 300,
  "max_ttl": 3600,
  "key_prefix": "tom_cache"
}
```

## Data Types

### JobResponse
```json
{
  "id": "job-uuid",
  "status": "pending|queued|active|succeeded|failed|aborted",
  "result": "command output (when completed)",
  "error": "error message (when failed)",
  "created_at": "2025-01-20T10:30:00Z",
  "started_at": "2025-01-20T10:30:05Z",
  "completed_at": "2025-01-20T10:30:10Z"
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
- `inventory_type`: "yaml" or "swis" (default: "yaml")
- `swapi_host`, `swapi_username`, `swapi_password`: SolarWinds connection (for swis inventory)
- `auth_mode`: "none", "api_key", "jwt", or "hybrid" (default: "none")
- `api_keys`: List of "key:user" pairs (when using api_key auth)
- `jwt_providers`: List of OAuth/OIDC provider configurations (when using jwt auth)
- `allowed_users`, `allowed_domains`, `allowed_user_regex`: Authorization settings (when using jwt auth)
- `cache_enabled`: Enable/disable caching (default: true)
- `cache_default_ttl`: Default cache TTL in seconds (default: 300)
- `cache_max_ttl`: Maximum allowed TTL in seconds (default: 3600)
- `cache_key_prefix`: Redis key prefix for cache entries (default: "tom_cache")

See `tom_config.jwt.example.yaml` for complete configuration examples.