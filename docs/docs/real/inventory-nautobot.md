# Nautobot Inventory

The Nautobot inventory plugin pulls device information from a Nautobot instance via its REST API. This allows Tom to use Nautobot as the source of truth for network devices.

## When to Use

If you have Nautobot, use it. A proper source of truth is preferable to an NMS like SolarWinds, and certainly better than maintaining YAML files by hand.

## Requirements

- Nautobot instance (1.x or 2.x)
- API token with read access to devices
- `pynautobot` library (included in Tom's dependencies)

## Configuration

### Controller Config

```yaml
# tom_controller_config.yaml
inventory_type: nautobot

# Plugin settings
plugin_nautobot_url: "https://nautobot.example.com"
plugin_nautobot_token: "your-api-token"

# Credential mapping (choose one)
plugin_nautobot_credential_source: custom_field  # or: config_context
plugin_nautobot_credential_field: credential_id  # custom field name
plugin_nautobot_credential_default: default      # fallback credential ID

# Optional: Filter which devices to include
plugin_nautobot_status_filter: ["Active"]
plugin_nautobot_role_filter: []
plugin_nautobot_location_filter: []
plugin_nautobot_tag_filter: []

# Defaults when platform data is missing
plugin_nautobot_default_adapter: netmiko
plugin_nautobot_default_driver: cisco_ios
```

Or via environment variables:

```bash
TOM_PLUGIN_NAUTOBOT_URL=https://nautobot.example.com
TOM_PLUGIN_NAUTOBOT_TOKEN=your-api-token
TOM_PLUGIN_NAUTOBOT_CREDENTIAL_SOURCE=custom_field
TOM_PLUGIN_NAUTOBOT_CREDENTIAL_FIELD=credential_id
```

## Credential Mapping

Tom needs to know which credential to use for each device. Nautobot doesn't store device credentials directly, so you map devices to credential IDs that exist in your credential store (Vault or YAML).

### Option 1: Custom Field (Recommended)

Create a custom field in Nautobot:

1. Go to **Extensibility > Custom Fields**
2. Create a new custom field:
   - Name: `credential_id`
   - Type: Text
   - Content Types: dcim | device
3. Set the credential ID on each device

Configure Tom to use it:

```yaml
plugin_nautobot_credential_source: custom_field
plugin_nautobot_credential_field: credential_id
plugin_nautobot_credential_default: default
```

### Option 2: Config Context

Use Nautobot config context for more complex scenarios:

```yaml
plugin_nautobot_credential_source: config_context
plugin_nautobot_credential_context_path: tom.credential_id
plugin_nautobot_credential_default: default
```

In Nautobot, add config context to devices (directly or via config context schema):

```json
{
  "tom": {
    "credential_id": "lab_creds"
  }
}
```

The path supports nested keys (e.g., `tom.credentials.ssh`).

## Adapter and Driver

Tom uses Nautobot's built-in `netmiko_device_type` field on the Platform model. If this field is not set, Tom falls back to the configured defaults.

### Nautobot Platform Setup

1. Go to **Devices > Platforms**
2. Edit each platform
3. Set the **Network Driver** field (e.g., `cisco_ios`, `arista_eos`)

### Defaults

If a platform doesn't have `netmiko_device_type` set, Tom uses:

```yaml
plugin_nautobot_default_adapter: netmiko
plugin_nautobot_default_driver: cisco_ios
```

## Device Filtering

Filter which devices Tom includes in its inventory:

```yaml
# Only include Active and Planned devices
plugin_nautobot_status_filter: ["Active", "Planned"]

# Only include specific roles
plugin_nautobot_role_filter: ["Edge Router", "Core Switch"]

# Only include specific locations
plugin_nautobot_location_filter: ["NYC-DC1", "SFO-DC2"]

# Only include devices with specific tags
plugin_nautobot_tag_filter: ["production", "tom-managed"]
```

Leave a filter empty (`[]`) to disable it. Multiple values in a filter use OR logic; multiple filters use AND logic.

## Host/IP Resolution

Tom determines the device IP in this order:

1. **primary_ip4** - IPv4 address (without prefix)
2. **primary_ip6** - IPv6 address (without prefix)
3. **Device name** - Falls back to using the device name as hostname

Ensure your devices have primary IPs assigned in Nautobot for reliable connectivity.

## Example: Complete Setup

### 1. Nautobot Setup

Create a custom field for credential mapping:
- Name: `credential_id`
- Type: Text
- Assign to devices

Configure your platforms with netmiko device types.

Assign primary IPs to devices.

### 2. Tom Configuration

```yaml
# tom_controller_config.yaml
inventory_type: nautobot

plugin_nautobot_url: "https://nautobot.example.com"
plugin_nautobot_token: "abc123def456"
plugin_nautobot_credential_source: custom_field
plugin_nautobot_credential_field: credential_id
plugin_nautobot_credential_default: default
plugin_nautobot_status_filter: ["Active"]
```

### 3. Store Credentials

Credentials referenced by `credential_id` must exist in your credential store:

```bash
# Using Vault
uv run credload.py put default -u admin -p defaultpass
uv run credload.py put lab_creds -u labuser -p labpass
```

### 4. Test

```bash
# List all devices from Nautobot
curl "http://localhost:8000/api/inventory/export" \
  -H "X-API-Key: your-api-key"

# Query a specific device
curl -X POST "http://localhost:8000/device/router1/send_command" \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{"command": "show version", "wait": true}'
```

## Troubleshooting

### "400" Errors from Nautobot

Filter values must exactly match what exists in Nautobot (case-sensitive). Nautobot uses title case for status values: `Active`, `Planned`, `Staged`, `Failed`, `Inventory`, `Decommissioning`, `Offline`.

Use empty filters to disable filtering and see all devices:

```yaml
plugin_nautobot_status_filter: []
```

## Filtering

### Config-Level Filters

These filters are applied when querying Nautobot and control which devices Tom knows about:

- `plugin_nautobot_status_filter`
- `plugin_nautobot_role_filter`
- `plugin_nautobot_location_filter`
- `plugin_nautobot_tag_filter`

### Inline API Filters

When exporting inventory via the API, you can filter on any field in the returned data:

| Field | Description |
|-------|-------------|
| `Caption` | Device name |
| `host` | IP address or hostname |
| `adapter` | netmiko or scrapli |
| `adapter_driver` | Platform driver |
| `credential_id` | Credential reference |

```bash
curl "http://localhost:8000/api/inventory/export?adapter_driver=cisco_ios" \
  -H "X-API-Key: your-api-key"
```
