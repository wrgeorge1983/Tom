# YAML Inventory

The YAML inventory plugin reads device information from a local YAML file.

## When to Use

Use YAML only if you don't have a source of truth (NetBox, Nautobot) or NMS (SolarWinds) available. It works, but you're manually maintaining device lists that should probably live somewhere else.

## Configuration

### Controller Config

```yaml
# tom_controller_config.yaml
inventory_type: yaml

# Plugin-specific settings
plugin_yaml_inventory_file: inventory/inventory.yml
```

Or via environment variable:

```bash
TOM_PLUGIN_YAML_INVENTORY_FILE=inventory/inventory.yml
```

The path is relative to `project_root` (defaults to `/app` in containers).

## Inventory File Format

```yaml
# inventory/inventory.yml

router1:
  host: "192.168.1.1"
  adapter: "netmiko"
  adapter_driver: "cisco_ios"
  credential_id: "lab_creds"
  port: 22

switch1:
  host: "192.168.1.10"
  adapter: "scrapli"
  adapter_driver: "cisco_iosxe"
  credential_id: "lab_creds"

arista-spine:
  host: "10.0.0.1"
  adapter: "netmiko"
  adapter_driver: "arista_eos"
  credential_id: "arista_creds"
  port: 22
```

### Required Fields

| Field | Description |
|-------|-------------|
| `host` | IP address or resolvable hostname |
| `adapter` | `netmiko` or `scrapli` |
| `adapter_driver` | Platform driver (see below) |
| `credential_id` | Reference to credential in Vault or YAML credential store |

### Optional Fields

| Field | Default | Description |
|-------|---------|-------------|
| `port` | 22 | SSH port |
| `adapter_options` | `{}` | Additional options passed to the adapter |

## Common Platform Drivers

### Netmiko Drivers

| Platform | Driver |
|----------|--------|
| Cisco IOS | `cisco_ios` |
| Cisco IOS-XE | `cisco_xe` |
| Cisco NX-OS | `cisco_nxos` |
| Cisco IOS-XR | `cisco_xr` |
| Arista EOS | `arista_eos` |
| Juniper Junos | `juniper_junos` |
| Dell OS10 | `dell_os10` |
| Palo Alto PAN-OS | `paloalto_panos` |

### Scrapli Drivers

| Platform | Driver |
|----------|--------|
| Cisco IOS-XE | `cisco_iosxe` |
| Cisco NX-OS | `cisco_nxos` |
| Cisco IOS-XR | `cisco_iosxr` |
| Arista EOS | `arista_eos` |
| Juniper Junos | `juniper_junos` |

See the [Netmiko](https://github.com/ktbyers/netmiko) and [Scrapli](https://carlmontanari.github.io/scrapli/) documentation for complete driver lists.

## Adapter Options

Pass adapter-specific options via `adapter_options`. These are passed directly to the underlying library (Netmiko or Scrapli), so any option supported by the library can be used here.

```yaml
slow-device:
  host: "10.0.0.50"
  adapter: "netmiko"
  adapter_driver: "cisco_ios"
  credential_id: "default"
  adapter_options:
    timeout: 60
    global_delay_factor: 2
```

See the [Netmiko](https://github.com/ktbyers/netmiko) and [Scrapli](https://carlmontanari.github.io/scrapli/) documentation for available options.

## Filterable Fields

The YAML plugin supports filtering on these fields:

| Field | Description |
|-------|-------------|
| `Caption` | Device name (the YAML key) |
| `host` | IP address or hostname |
| `adapter` | netmiko or scrapli |
| `adapter_driver` | Platform driver |
| `credential_id` | Credential reference |
| `port` | SSH port |

Example filter:

```bash
curl "http://localhost:8000/api/inventory/export?adapter_driver=cisco_ios"
```

## Example: Complete Setup

### 1. Create inventory file

```yaml
# inventory/inventory.yml
core-rtr-01:
  host: "10.1.1.1"
  adapter: "netmiko"
  adapter_driver: "cisco_ios"
  credential_id: "network_creds"

core-rtr-02:
  host: "10.1.1.2"
  adapter: "netmiko"
  adapter_driver: "cisco_ios"
  credential_id: "network_creds"

dc-sw-01:
  host: "10.1.2.1"
  adapter: "scrapli"
  adapter_driver: "arista_eos"
  credential_id: "arista_creds"
```

### 2. Configure controller

```yaml
# tom_controller_config.yaml
inventory_type: yaml
plugin_yaml_inventory_file: inventory/inventory.yml
```

### 3. Store credentials

Using Vault (recommended):

```bash
uv run credload.py put network_creds -u admin -p secretpass
uv run credload.py put arista_creds -u arista -p aristapass
```

Or using YAML credentials (not recommended for production):

```yaml
# inventory/creds.yml
network_creds:
  username: admin
  password: secretpass

arista_creds:
  username: arista
  password: aristapass
```

### 4. Test

```bash
curl -X POST "http://localhost:8000/api/device/core-rtr-01/send_command" \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{"command": "show version", "wait": true}'
```
