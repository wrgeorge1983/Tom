# SolarWinds Inventory

The SolarWinds inventory plugin pulls device information from SolarWinds NPM (Network Performance Monitor) via the SWIS (SolarWinds Information Service) API.

## When to Use

If SolarWinds is what you have, it works. A proper source of truth like NetBox or Nautobot is preferable since they're designed for this purpose, but SolarWinds is still better than maintaining YAML files by hand.

## Requirements

- SolarWinds NPM/Orion instance
- SWIS API access (typically port 17774)
- User account with API permissions
- `orionsdk` library (included in Tom's dependencies)

## Configuration

### Controller Config

```yaml
# tom_controller_config.yaml
inventory_type: solarwinds

# Plugin settings
plugin_solarwinds_host: "solarwinds.example.com"
plugin_solarwinds_username: "apiuser"
plugin_solarwinds_password: "apipassword"
plugin_solarwinds_port: 17774

# Default credential ID for devices
plugin_solarwinds_default_cred_name: default

# Device mappings (see below)
plugin_solarwinds_device_mappings:
  - match:
      vendor: "cisco"
      description: "ios"
    action:
      adapter: netmiko
      adapter_driver: cisco_ios
      credential_id: cisco_creds
  - match:
      vendor: "arista"
    action:
      adapter: netmiko
      adapter_driver: arista_eos
      credential_id: arista_creds
  - match:
      vendor: ".*"
    action:
      adapter: netmiko
      adapter_driver: cisco_ios
      credential_id: default
```

Or via environment variables:

```bash
TOM_PLUGIN_SOLARWINDS_HOST=solarwinds.example.com
TOM_PLUGIN_SOLARWINDS_USERNAME=apiuser
TOM_PLUGIN_SOLARWINDS_PASSWORD=apipassword
TOM_PLUGIN_SOLARWINDS_PORT=17774
```

## Device Mappings

SolarWinds doesn't store netmiko/scrapli driver information, so you configure rules to map devices to adapters based on their SolarWinds properties.

Each mapping rule has:

- **match**: Regex patterns to match against device properties
- **action**: What adapter/driver/credential to use for matching devices

```yaml
plugin_solarwinds_device_mappings:
  # Cisco IOS devices
  - match:
      vendor: "cisco"
      description: "(?i)ios(?!-xr)"  # IOS but not IOS-XR
    action:
      adapter: netmiko
      adapter_driver: cisco_ios
      credential_id: cisco_creds

  # Cisco IOS-XR devices
  - match:
      vendor: "cisco"
      description: "(?i)ios-xr"
    action:
      adapter: netmiko
      adapter_driver: cisco_xr
      credential_id: cisco_creds

  # Arista switches
  - match:
      vendor: "arista"
    action:
      adapter: netmiko
      adapter_driver: arista_eos
      credential_id: arista_creds

  # Juniper devices
  - match:
      vendor: "juniper"
    action:
      adapter: netmiko
      adapter_driver: juniper_junos
      credential_id: juniper_creds

  # Catch-all fallback (should be last)
  - match:
      vendor: ".*"
    action:
      adapter: netmiko
      adapter_driver: cisco_ios
      credential_id: default
```

### Match Criteria

| Field | SolarWinds Property | Description |
|-------|---------------------|-------------|
| `vendor` | `Vendor` | Device vendor (regex) |
| `description` | `Description` | Device description/OS (regex) |
| `caption` | `Caption` | Device hostname (regex) |

All patterns are case-insensitive regex. Rules are evaluated in order; first match wins.

## Named Filters

*Note: Named filters may be deprecated in a future release. Prefer inline filters for new implementations.*

The SolarWinds plugin includes predefined filters for common device types:

| Filter Name | Description |
|-------------|-------------|
| `switches` | Dell, Arista, and Cisco switches |
| `routers` | Cisco ASR and Juniper MX routers |
| `arista_exclusion` | Arista devices excluding specific models |
| `iosxe` | Cisco IOS-XE devices (excludes Nexus, ASA) |
| `ospf_crawler_filter` | Cisco ASR, 29xx, Juniper MX104 |

Use named filters:

```bash
curl "http://localhost:8000/api/inventory/export?filter_name=switches" \
  -H "X-API-Key: your-api-key"
```

## Filterable Fields

The SolarWinds plugin supports filtering on these fields:

| Field | Description |
|-------|-------------|
| `NodeID` | SolarWinds node ID |
| `IPAddress` | Device IP address |
| `Uri` | SolarWinds URI |
| `Caption` | Device hostname |
| `Description` | Device description/OS info |
| `Status` | Node status code |
| `Vendor` | Device vendor |
| `DetailsUrl` | SolarWinds details URL |

Example inline filter:

```bash
curl "http://localhost:8000/api/inventory/export?Vendor=cisco&Description=asr.*" \
  -H "X-API-Key: your-api-key"
```

## Device Data

The plugin queries SolarWinds for nodes with status 1 (Up) or 3 (Warning) by default. For each node, it retrieves:

- `NodeID` - SolarWinds internal ID
- `IPAddress` - Used as the connection host
- `Caption` - Used as the device name
- `Vendor` - Used for device mapping
- `Description` - Used for device mapping

## Example: Complete Setup

### 1. SolarWinds Setup

Ensure your SolarWinds instance has:
- SWIS API enabled (port 17774)
- A user account with API read permissions
- Nodes with Vendor and Description populated

### 2. Tom Configuration

```yaml
# tom_controller_config.yaml
inventory_type: solarwinds

plugin_solarwinds_host: "solarwinds.example.com"
plugin_solarwinds_username: "tom_api"
plugin_solarwinds_password: "secretpassword"
plugin_solarwinds_port: 17774
plugin_solarwinds_default_cred_name: default

plugin_solarwinds_device_mappings:
  - match:
      vendor: "cisco"
    action:
      adapter: netmiko
      adapter_driver: cisco_ios
      credential_id: cisco_creds
  - match:
      vendor: "arista"
    action:
      adapter: netmiko
      adapter_driver: arista_eos
      credential_id: arista_creds
  - match:
      vendor: ".*"
    action:
      adapter: netmiko
      adapter_driver: cisco_ios
      credential_id: default
```

### 3. Store Credentials

```bash
# Using Vault
uv run credload.py put default -u admin -p defaultpass
uv run credload.py put cisco_creds -u cisco -p ciscopass
uv run credload.py put arista_creds -u arista -p aristapass
```

### 4. Test

```bash
# List all devices from SolarWinds
curl "http://localhost:8000/api/inventory/export" \
  -H "X-API-Key: your-api-key"

# List only switches
curl "http://localhost:8000/api/inventory/export?filter_name=switches" \
  -H "X-API-Key: your-api-key"

# Query a specific device (by Caption/hostname)
curl -X POST "http://localhost:8000/device/core-rtr-01/send_command" \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{"command": "show version", "wait": true}'
```
