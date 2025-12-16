# Setting Up Devices in Nautobot for Tom

This guide walks through configuring a device in Nautobot so that Tom can manage it.

## Prerequisites

Before adding devices, ensure:

1. **Tom is configured for Nautobot** - See [Nautobot Inventory](inventory-nautobot.md)
2. **Credential mapping is configured** - Either custom field or config context
3. **Credentials are stored in Vault** - See [Vault Credentials](vault-credentials.md)

### Credential Mapping Options

Tom can read credential IDs from either a **custom field** or **config context**. See [Nautobot Inventory](inventory-nautobot.md) for full configuration options.

#### Option A: Custom Field (Default)

Create a custom field in Nautobot:

1. Go to **Extensibility > Custom Fields**
2. Click **Add**
3. Configure:
   - **Content Types**: `dcim | device`
   - **Type**: Text
   - **Label**: `credential_id`
   - **Key**: `credential_id`
4. Save

#### Option B: Config Context

No custom field needed. Add credential info to device config context:

```json
{
  "tom": {
    "credential_id": "my_creds"
  }
}
```

Configure Tom to read from config context:
```yaml
plugin_nautobot_credential_source: config_context
plugin_nautobot_credential_field: tom.credential_id
```

## Adding a Device

### Step 1: Create Prefix (if needed)

The management IP must belong to a prefix. If the subnet doesn't exist:

1. Go to **IPAM > Prefixes**
2. Click **Add**
3. Enter the prefix (e.g., `10.1.2.0/24`)
4. Set **Status** to Active
5. Save

### Step 2: Create IP Address

1. Go to **IPAM > IP Addresses**
2. Click **Add**
3. Enter the management IP with mask (e.g., `10.1.2.3/32`)
4. Set **Status** to Active
5. Save

Note: The IP must fall within an existing prefix.

### Step 3: Create Device

1. Go to **Devices > Devices**
2. Click **Add**
3. Fill in required fields:
   - **Name**: Device hostname
   - **Device Type**: Select appropriate type
   - **Role**: Select role (e.g., Router, Switch)
   - **Location**: Select location
   - **Status**: Active
4. Set **Platform** (optional but recommended):
   - Select a platform that has `netmiko_device_type` configured
   - If not set, Tom uses its default driver
5. Set the **credential_id** custom field:
   - Enter the credential name stored in Vault
6. Save (don't set Primary IP yet - we need an interface first)

### Step 4: Create Interface

1. On the device page, go to **Interfaces**
2. Click **Add**
3. Configure:
   - **Name**: Interface name (e.g., `Management0`, `GigabitEthernet0/0`)
   - **Type**: Select appropriate type
4. Save

Note: Interfaces can also be on modules (line cards) rather than directly on the device.

### Step 5: Assign IP to Interface

1. Edit the interface created in Step 4
2. In **IP Addresses**, select the IP created in Step 2
3. Save

Alternatively, edit the IP address and assign it to the interface from there.

### Step 6: Set Primary IP

1. Edit the device
2. Set **Primary IPv4** to the management IP
3. Save

The Primary IP dropdown only shows IPs assigned to the device's interfaces.

### Step 7: Store Credential in Vault

If the credential doesn't already exist:

```bash
uv run credload.py put <credential_id> -u <username> -p <password>
```

The `<credential_id>` must match what you entered in the device's custom field.

## Verification

### Check Device in Tom

```bash
# List all devices Tom can see
curl "http://localhost:8000/api/inventory/export" \
  -H "X-API-Key: your-api-key"

# Check specific device
curl -X POST "http://localhost:8000/api/device/<device-name>/send_command" \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{"command": "show version", "wait": true}'
```

### What Tom Reads from Nautobot

| Tom Field | Nautobot Source (configurable) |
|-----------|--------------------------------|
| Host/IP | `primary_ip4` (or `primary_ip6`, or device name as fallback) |
| Credential | Custom field or config context (per `credential_source` setting) |
| Adapter | Custom field or config context (per `adapter_source` setting), or default |
| Driver | Custom field or config context (per `driver_source` setting), or default |

See [Nautobot Inventory](inventory-nautobot.md) for full configuration options.

## Example: Working Device

The minimum fields Tom needs from a Nautobot device:

| Field | Example | Notes |
|-------|---------|-------|
| Name | `router1` | Device identifier |
| Status | Active | Must match Tom's status filter |
| Primary IPv4 | `10.1.2.3/32` | How Tom connects to the device |
| Credential ID | `lab_creds` | Via custom field or config context; must exist in Vault |

## Troubleshooting

### Device Not Found in Tom

1. Check the device exists in Nautobot
2. Verify device status matches Tom's filter (default: `Active`)
3. Check Tom controller logs for Nautobot API errors

### Connection Failures

1. Verify `primary_ip4` is set and reachable
2. Check `credential_id` matches a credential in Vault
3. Verify the credential has correct username/password
4. Check platform driver is correct for the device OS

### Wrong Driver Being Used

1. Check if device has a platform assigned
2. Verify platform has `netmiko_device_type` set
3. Or update Tom's default driver in config

### List Credentials in Vault

```bash
uv run credload.py list
```
