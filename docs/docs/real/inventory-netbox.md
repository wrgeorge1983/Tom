# NetBox Inventory

The NetBox inventory plugin pulls device information from a NetBox instance via its REST API. This allows Tom to use NetBox as the source of truth for network devices.

## When to Use

If you have NetBox, use it. A proper source of truth is preferable to an NMS like SolarWinds, and certainly better than maintaining YAML files by hand.

## Requirements

- NetBox instance (3.x or 4.x)
- API token with read access to devices
- `pynetbox` library (included in Tom's dependencies)

## Configuration

### Controller Config

```yaml
# tom_controller_config.yaml
inventory_type: netbox

# Plugin settings
plugin_netbox_url: "https://netbox.example.com"
plugin_netbox_token: "your-api-token"

# Credential mapping (choose one)
plugin_netbox_credential_source: custom_field  # or: config_context
plugin_netbox_credential_field: credential_id  # custom field name
plugin_netbox_credential_default: default      # fallback credential ID

# Adapter/driver - either use defaults for all devices, or specify custom fields
plugin_netbox_default_adapter: netmiko
plugin_netbox_default_driver: cisco_ios

# Optional: custom fields on devices to override defaults
# plugin_netbox_adapter_custom_field: tom_adapter  # e.g., "netmiko" or "scrapli"
# plugin_netbox_driver_custom_field: tom_driver    # e.g., "cisco_ios"

# Optional: Filter which devices to include
plugin_netbox_status_filter: ["active"]
plugin_netbox_role_filter: []
plugin_netbox_location_filter: []
plugin_netbox_tag_filter: []
```

Or via environment variables:

```bash
TOM_PLUGIN_NETBOX_URL=https://netbox.example.com
TOM_PLUGIN_NETBOX_TOKEN=your-api-token
TOM_PLUGIN_NETBOX_CREDENTIAL_SOURCE=custom_field
TOM_PLUGIN_NETBOX_CREDENTIAL_FIELD=credential_id
```

## Credential Mapping

Tom needs to know which credential to use for each device. NetBox doesn't store credentials, so you map devices to credential IDs that exist in your credential store (Vault or YAML).

### Option 1: Custom Field (Recommended)

Create a custom field in NetBox:

1. Go to **Customization > Custom Fields**
2. Create a new custom field:
   - Name: `credential_id`
   - Type: Text
   - Content Types: dcim > device
3. Set the credential ID on each device

Configure Tom to use it:

```yaml
plugin_netbox_credential_source: custom_field
plugin_netbox_credential_field: credential_id
plugin_netbox_credential_default: default
```

### Option 2: Config Context

Use NetBox config context for more complex scenarios:

```yaml
plugin_netbox_credential_source: config_context
plugin_netbox_credential_context_path: tom.credential_id
plugin_netbox_credential_default: default
```

In NetBox, add config context to devices:

```json
{
  "tom": {
    "credential_id": "lab_creds"
  }
}
```

The path supports nested keys (e.g., `tom.credentials.ssh`).

## Adapter and Driver

NetBox doesn't have built-in fields for network automation drivers. You have two options:

### Option 1: Use Defaults (Simple)

If all your devices use the same adapter and driver, just set defaults:

```yaml
plugin_netbox_default_adapter: netmiko
plugin_netbox_default_driver: cisco_ios
```

### Option 2: Use Custom Fields (Per-Device)

For mixed environments, create custom fields in NetBox and configure Tom to read them:

1. In NetBox, create custom fields on the Device model (e.g., `tom_adapter`, `tom_driver`)
2. Set values on your devices
3. Configure Tom to use them:

```yaml
plugin_netbox_adapter_custom_field: tom_adapter
plugin_netbox_driver_custom_field: tom_driver

# Defaults for devices without custom field values
plugin_netbox_default_adapter: netmiko
plugin_netbox_default_driver: cisco_ios
```

## Device Filtering

Filter which devices Tom includes in its inventory:

```yaml
# Only include active and staged devices
plugin_netbox_status_filter: ["active", "staged"]

# Only include specific roles
plugin_netbox_role_filter: ["Edge Router", "Core Switch"]

# Only include specific locations
plugin_netbox_location_filter: ["NYC-DC1", "SFO-DC2"]

# Only include devices with specific tags
plugin_netbox_tag_filter: ["production", "tom-managed"]
```

Leave a filter empty (`[]`) to disable it. Multiple values in a filter use OR logic; multiple filters use AND logic.

## Host/IP Resolution

Tom determines the device IP in this order:

1. **primary_ip4** - IPv4 address (without prefix)
2. **primary_ip6** - IPv6 address (without prefix)
3. **Device name** - Falls back to using the device name as hostname

Ensure your devices have primary IPs assigned in NetBox for reliable connectivity.

## Example: Complete Setup

### 1. NetBox Setup

Create a custom field for credential mapping:
- Name: `credential_id`
- Type: Text
- Assign to devices

Configure your platforms with netmiko drivers.

Assign primary IPs to devices.

### 2. Tom Configuration

```yaml
# tom_controller_config.yaml
inventory_type: netbox

plugin_netbox_url: "https://netbox.example.com"
plugin_netbox_token: "abc123def456"
plugin_netbox_credential_source: custom_field
plugin_netbox_credential_field: credential_id
plugin_netbox_credential_default: default
plugin_netbox_status_filter: ["active"]
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
# List all devices from NetBox
curl "http://localhost:8000/api/inventory/export" \
  -H "X-API-Key: your-api-key"

# Query a specific device
curl -X POST "http://localhost:8000/device/router1/send_command" \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{"command": "show version", "wait": true}'
```

## Troubleshooting

### "400" Errors from NetBox

Filter values must exactly match what exists in NetBox (case-sensitive). NetBox uses lowercase for status values: `active`, `planned`, `staged`, `failed`, `inventory`, `decommissioning`, `offline`.

Use empty filters to disable filtering and see all devices:

```yaml
plugin_netbox_status_filter: []
```


## Filtering

### Config-Level Filters

These filters are applied when querying NetBox and control which devices Tom knows about:

- `plugin_netbox_status_filter`
- `plugin_netbox_role_filter`
- `plugin_netbox_location_filter`
- `plugin_netbox_tag_filter`

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
