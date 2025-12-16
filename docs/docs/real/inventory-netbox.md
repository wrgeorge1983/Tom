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

# Credential mapping
plugin_netbox_credential_source: custom_field  # or: config_context
plugin_netbox_credential_field: credential_id  # field name or config context path
plugin_netbox_default_credential: default      # fallback credential ID

# Adapter/driver mapping (optional - defaults work for most setups)
plugin_netbox_adapter_source: custom_field     # or: config_context
plugin_netbox_adapter_field: ""                # empty = use default
plugin_netbox_default_adapter: netmiko

plugin_netbox_driver_source: custom_field      # or: config_context
plugin_netbox_driver_field: ""                 # empty = use default
plugin_netbox_default_driver: cisco_ios

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

## Field Mapping

Tom needs to know the credential, adapter, and driver for each device. Each field can be sourced independently from either a **custom field** or **config context**.

### Settings Per Field

| Field | Source Setting | Field/Path Setting | Default Setting |
|-------|----------------|-------------------|-----------------|
| Credential | `credential_source` | `credential_field` | `default_credential` |
| Adapter | `adapter_source` | `adapter_field` | `default_adapter` |
| Driver | `driver_source` | `driver_field` | `default_driver` |

- **Source**: `custom_field` or `config_context`
- **Field**: Custom field name (e.g., `credential_id`) or config context path (e.g., `tom.credential_id`)
- **Default**: Fallback value when field is empty or not found

### Option 1: Custom Fields

Create custom fields in NetBox:

1. Go to **Customization > Custom Fields**
2. Create custom fields:
   - `credential_id` (Text) - required
   - `tom_adapter` (Text) - optional
   - `tom_driver` (Text) - optional
3. Content Types: dcim > device
4. Set values on each device

Configure Tom:

```yaml
plugin_netbox_credential_source: custom_field
plugin_netbox_credential_field: credential_id
plugin_netbox_default_credential: default

plugin_netbox_adapter_source: custom_field
plugin_netbox_adapter_field: tom_adapter    # or empty to use default
plugin_netbox_default_adapter: netmiko

plugin_netbox_driver_source: custom_field
plugin_netbox_driver_field: tom_driver      # or empty to use default
plugin_netbox_default_driver: cisco_ios
```

### Option 2: Config Context

Use NetBox config context for all Tom settings (no custom fields required):

```yaml
plugin_netbox_credential_source: config_context
plugin_netbox_credential_field: tom.credential_id

plugin_netbox_adapter_source: config_context
plugin_netbox_adapter_field: tom.adapter

plugin_netbox_driver_source: config_context
plugin_netbox_driver_field: tom.driver
```

In NetBox, add config context to devices:

```json
{
  "tom": {
    "credential_id": "lab_creds",
    "adapter": "netmiko",
    "driver": "cisco_ios"
  }
}
```

Config context paths support nesting (e.g., `tom.network.credential_id`).

### Option 3: Mixed Sources

You can mix sources - for example, credential from custom field, driver from config context:

```yaml
plugin_netbox_credential_source: custom_field
plugin_netbox_credential_field: credential_id

plugin_netbox_driver_source: config_context
plugin_netbox_driver_field: tom.driver
```

### Minimal Setup

If all devices use the same adapter/driver, just configure credentials:

```yaml
plugin_netbox_credential_source: custom_field
plugin_netbox_credential_field: credential_id
plugin_netbox_default_adapter: netmiko
plugin_netbox_default_driver: cisco_ios
```

Leave `adapter_field` and `driver_field` empty (or omit them) to use defaults.

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

Assign primary IPs to devices.

### 2. Tom Configuration

```yaml
# tom_controller_config.yaml
inventory_type: netbox

plugin_netbox_url: "https://netbox.example.com"
plugin_netbox_token: "abc123def456"
plugin_netbox_credential_source: custom_field
plugin_netbox_credential_field: credential_id
plugin_netbox_default_credential: default
plugin_netbox_default_adapter: netmiko
plugin_netbox_default_driver: cisco_ios
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
curl -X POST "http://localhost:8000/api/device/router1/send_command" \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{"command": "show version", "wait": true}'
```

## Settings Reference

| Setting | Default | Description |
|---------|---------|-------------|
| `url` | (required) | NetBox URL |
| `token` | (required) | API token |
| `credential_source` | `custom_field` | `custom_field` or `config_context` |
| `credential_field` | `credential_id` | Field name or config context path |
| `default_credential` | `default` | Fallback credential ID |
| `adapter_source` | `custom_field` | `custom_field` or `config_context` |
| `adapter_field` | `""` | Field name or config context path (empty = use default) |
| `default_adapter` | `netmiko` | `netmiko` or `scrapli` |
| `driver_source` | `custom_field` | `custom_field` or `config_context` |
| `driver_field` | `""` | Field name or config context path (empty = use default) |
| `default_driver` | `cisco_ios` | Netmiko/Scrapli driver name |
| `default_port` | `22` | SSH port |
| `status_filter` | `[]` | Filter by device status |
| `role_filter` | `[]` | Filter by device role |
| `location_filter` | `[]` | Filter by location |
| `tag_filter` | `[]` | Filter by tags |

## Troubleshooting

### "400" Errors from NetBox

Filter values must exactly match what exists in NetBox (case-sensitive). NetBox uses lowercase for status values: `active`, `planned`, `staged`, `failed`, `inventory`, `decommissioning`, `offline`.

Use empty filters to disable filtering and see all devices:

```yaml
plugin_netbox_status_filter: []
```

### Device Not Using Expected Driver

Check the order of precedence:
1. If `driver_field` is set and device has a value, that's used
2. Otherwise `default_driver` is used

To debug, export inventory and check what Tom sees:

```bash
curl "http://localhost:8000/api/inventory/export" -H "X-API-Key: your-key"
```
