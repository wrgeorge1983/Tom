# Inventory

The inventory tells Tom which devices exist and how to connect to them. Tom supports multiple inventory sources through a plugin system.

## How It Works

When you request a command on a device (e.g., `POST /device/router1/send_command`), Tom looks up `router1` in the configured inventory source to get:

- **host**: IP address or hostname
- **adapter**: Connection library (`netmiko` or `scrapli`)
- **adapter_driver**: Platform type (`cisco_ios`, `arista_eos`, etc.)
- **credential_id**: Reference to credentials in the credential store
- **port**: SSH port (default 22)

The inventory only stores a `credential_id` reference, not actual credentials. Workers retrieve the real username/password from the credential store (Vault or YAML) at execution time.

## Supported Inventory Sources

| Plugin | Use Case | Documentation |
|--------|----------|---------------|
| [YAML](inventory-yaml.md) | Simple setups, testing, small environments | Local file |
| [NetBox](inventory-netbox.md) | NetBox as source of truth | API integration |
| [Nautobot](inventory-nautobot.md) | Nautobot as source of truth | API integration |
| [SolarWinds](inventory-solarwinds.md) | SolarWinds NPM environments | SWIS API integration |

## Configuration

Set the inventory type in your controller config:

```yaml
# tom_controller_config.yaml
inventory_type: yaml  # or: netbox, nautobot, solarwinds
```

Each plugin has its own configuration options, documented on its respective page.

## Plugin Priority

When multiple inventory plugins are configured, Tom uses priority to determine which one to query first. Lower numbers = higher priority.

```yaml
# Default priorities
inventory_plugins:
  yaml: 100
  nautobot: 150
  netbox: 160
  solarwinds: 200
```

In practice, most deployments probably use a single inventory source.

## DeviceConfig Structure

All inventory plugins return the same `DeviceConfig` structure:

```python
class DeviceConfig:
    host: str                    # IP or hostname
    adapter: str                 # "netmiko" or "scrapli"
    adapter_driver: str          # Platform driver
    credential_id: str           # Reference to credential store
    port: int = 22               # SSH port
    adapter_options: dict = {}   # Optional adapter-specific settings
```

## Inventory API Endpoints

Tom exposes several inventory-related API endpoints:

```bash
# Get a single device's config
GET /api/inventory/{device_name}

# Export all devices
GET /api/inventory/export

# Export raw inventory data (plugin-specific format)
GET /api/inventory/export/raw

# List filterable fields for current inventory source
GET /api/inventory/fields

# List available named filters
GET /api/inventory/filters
```

## Filtering

Some inventory plugins support filtering the device list:

### Named Filters

*Note: Named filters may be deprecated in a future release. Prefer inline filters.* 

Predefined filters for common use cases:

```bash
curl "http://localhost:8000/api/inventory/export?filter_name=switches"
```

### Inline Filters

Filter by field values using regex patterns:

```bash
# Filter by vendor and description
curl "http://localhost:8000/api/inventory/export?Vendor=cisco&Description=asr.*"
```

Available fields vary by inventory source. Use `GET /api/inventory/fields` to see what's available.

## Choosing an Inventory Source

If you have a source of truth (NetBox, Nautobot), use it. If you only have an NMS (SolarWinds), that works too. YAML is a fallback for when you don't have anything better - it works, but you're manually maintaining device lists that should probably live somewhere else.
