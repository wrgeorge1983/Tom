# Tom Tutorial Setup

This tutorial setup demonstrates Tom Smykowski integrated with your existing Nautobot instance as the source of truth.

## What's Included

- **Tom Controller** - API server on port 8000
- **Tom Workers** (3 replicas) - Execute commands on network devices
- **Redis** - Job queue and cache for Tom
- **Vault** - Credential storage (dev mode)

## Prerequisites

- Docker and Docker Compose
- Python 3.13+ and [uv](https://docs.astral.sh/uv)
- An existing Nautobot instance with devices configured
- Network devices accessible via SSH from the Docker host
- API token for your Nautobot instance

## Quick Start

### 1. Configure Tom for Your Nautobot

Edit `tom_controller_config.yaml` and update:

```yaml
# Point to your Nautobot instance
plugin_nautobot_url: "https://your-nautobot.example.com"
plugin_nautobot_token: "your-nautobot-api-token"

# Update credential field name if different
plugin_nautobot_credential_field: "credential_id"
plugin_nautobot_default_credential: "default_creds"
```

### 2. Generate a Secure API Key

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Update `tom_controller_config.yaml`:

```yaml
api_keys: ["your-generated-key-here:admin"]
```

### 3. Start Tom Services

```bash
cd tutorial-configs
docker compose up -d
```

Verify services are running:

```bash
docker compose ps
```

### 4. Store Device Credentials in Vault

From the repo root directory, store credentials that match the `credential_id` values on your Nautobot devices:

```bash
# Store credentials for your devices
uv run credload.py put default_creds -u admin -p your-device-password
uv run credload.py put context_configs -u cisco -p cisco-password
# etc.
```

### 5. Test Tom

```bash
# List inventory from Nautobot
curl "http://localhost:8000/api/inventory/export" \
  -H "X-API-Key: your-generated-key-here"

curl "http://localhost:8000/api/credentials" \
  -H "X-API-KEY: your-generated-key-here"

# Send a command to a device (use a device name from your Nautobot)
curl -X POST "http://localhost:8000/api/device/your-device-name/send_command" \
  -H "X-API-Key: your-generated-key-here" \
  -H "Content-Type: application/json" \
  -d '{
    "command": "show version",
    "wait": true
  }'
```

## Architecture
```
               ┌─────────────┐
               │  Nautobot   │
               │  (Your SoT) │
               │  (external) │
               └──────┬──────┘
                      │ inventory
                      │ queries
┌─────────┐     ┌─────┴───────┐     ┌─────────────┐     ┌─────────┐
│ Client  │────►│ Controller  │────►│    Redis    │─────│ Workers │
│         │     │             │     │   (queue)   │     │  (x3)   │
└─────────┘     └─────────────┘     └─────────────┘     └────┬────┘
                                                             │credentials
                                                      ┌─────────────┐
                                                      │    Vault    │
                                                      │(credentials)│   
                                                      └─────────────┘
```

## Services and Ports

| Service | Port | Description |
|---------|------|-------------|
| Tom Controller | 8000 | Tom API server |
| Vault | 8200 | Vault UI (dev mode) |
| Redis | 6379 | Tom's Redis (queue/cache) |

## Nautobot Setup Requirements

For Tom to work with your Nautobot, devices need:

1. **Primary IP assigned** - Tom uses this to connect to devices
2. **Platform with netmiko_device_type** - Nautobot's Platform model has a field for this
3. **Credential ID** - Either via custom field or config context (see below)

### Credential Mapping Options

**Option 1: Custom Field (Recommended)**

Create a custom field on Device objects in Nautobot:
- Name: `credential_id`
- Type: Text

Set this field on each device to reference a credential stored in Vault.

**Option 2: Config Context**

Add config context to devices:

```json
{
  "tom": {
    "credential_id": "my_creds"
  }
}
```

Update `tom_controller_config.yaml`:

```yaml
plugin_nautobot_credential_source: "config_context"
plugin_nautobot_credential_field: "tom.credential_id"
```

## Configuration Files

| File | Purpose |
|------|---------|
| `docker-compose.yml` | Tom service definitions |
| `tom_controller_config.yaml` | Tom controller configuration |

## How Tom Uses Nautobot

1. **Inventory Lookup**: When you request a device by name, Tom queries Nautobot
2. **Connection Info**: Tom gets the device's primary IP and platform (netmiko driver)
3. **Credential Reference**: Tom reads the credential ID from custom field or config context
4. **Credential Fetch**: Workers fetch actual username/password from Vault
5. **Command Execution**: Workers connect to the device and execute commands

## Troubleshooting

### Tom Can't Reach Nautobot

Verify network connectivity from Docker:

```bash
docker compose exec controller curl -I https://your-nautobot.example.com
```

Check the Nautobot URL and token in `tom_controller_config.yaml`.

### Device Not Found

Verify the device exists in Nautobot and matches your status filter:

```yaml
# In tom_controller_config.yaml - Nautobot uses title case
plugin_nautobot_status_filter: ["Active"]
```

### Authentication Errors from Devices

1. Verify credentials are stored in Vault: `uv run credload.py list`
2. Check the device's credential_id field in Nautobot
3. Verify device primary IP is correct in Nautobot
4. Check worker logs: `docker compose logs worker`

### View Tom Logs

```bash
docker compose logs controller
docker compose logs worker
```

### Validate Configuration

From the services/controller directory:

```bash
uv run tom-controller-validate /path/to/tom_controller_config.yaml
```

## Cleanup

Stop and remove all containers:

```bash
docker compose down -v
```

## Next Steps

After completing the tutorial:

1. **Explore Parsing**: Add `"parse": true` to command requests
2. **Try Caching**: Use `"use_cache": true` and `"cache_ttl": 300`
3. **Multiple Commands**: Use `/api/device/{name}/send_commands` endpoint
4. **API Docs**: Visit http://localhost:8000/docs for Swagger UI
5. **Production Setup**: See the [sensible-configs](../sensible-configs/) for Redis TLS and better security
