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

#### Inventory-based Command
```
GET /api/device/{device_name}/send_command
```

**Parameters:**
- `device_name` (string): Device name from inventory
- `command` (string): Command to execute
- `wait` (bool, optional): Wait for job completion (default: false)
- `rawOutput` (bool, optional): Return raw output (requires wait=true)
- `timeout` (int, optional): Timeout in seconds (default: 10)
- Optional credential override:
  - `username` + `password` (string): Override inventory credentials

**Returns:** `JobResponse` or raw string (if rawOutput=true)

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

See `tom_config.jwt.example.yaml` for complete configuration examples.