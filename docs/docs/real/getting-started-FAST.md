# Getting Started Fast

Get Tom running and execute your first network command in under 10 minutes.

**WARNING: This setup prioritizes speed over security. It's good enough for a quick smoke test "does the thing do the thing" for lab testing but NOT for anything like production or even testing most of Tom's features.** For a better look at what it looks like in that mode take a look at [Getting Started Sensibly](getting-started.md). 

## Prerequisites

- Docker and Docker Compose installed
- Some current version of Python installed.
- At least one network device you can SSH to
- Device credentials (username/password)
    - Credentials YOU ARE ALLOWED TO TREAT INSECURELY!
    - This procedure is NOT doing anything to keep your creds particularly safe! For that see [Getting Started Sensibly](getting-started.md)   


## Step 1: Clone and Enter Quickstart Directory

```bash
git clone https://github.com/wrgeorge1983/tom.git
cd tom/quickstart-configs
```

## Step 2: Generate Your API Key

Generate a secure API key:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Copy the output - you'll need it in the next steps.

## Step 3: Configure Your API Key

Edit `tom_controller_config.yaml` and replace `REPLACE_ME_WITH_YOUR_API_KEY` with your generated API key from Step 2.

**Line 15 in tom_controller_config.yaml:**
```yaml
api_keys: ["your-generated-key-here:admin"]
```

## Step 4: Add Your Device

Edit `inventory/inventory.yml` and replace the example device with your actual device:

```yaml
my-router:
  host: "10.1.1.1"              # Your device IP
  adapter: "netmiko"
  adapter_driver: "cisco_ios"   # Match your platform
  port: 22
  credential_id: "unused"       # Required field, but we'll pass credentials via API
```

Common platform values:
- Cisco IOS: `cisco_ios`
- Cisco IOS-XE: `cisco_iosxe` (use `scrapli` adapter)
- Cisco NX-OS: `cisco_nxos`
- Arista EOS: `arista_eos`
- Juniper Junos: `juniper_junos`

**Note:** Credentials are passed via the API request (see Step 6), not stored in the inventory file.

## Step 5: Start Services

```bash
docker compose up
```

**Leave this running in the foreground** - you'll see logs from all services. This makes it easy to see what's happening and catch any issues.

Wait until you see log messages indicating the controller is ready (look for "Uvicorn running" or "Application startup complete").

**Open a new terminal** for the next step. Navigate back to the quickstart directory:
```bash
cd tom/quickstart-configs
```

## Step 6: Test It

```bash
curl -X POST "http://localhost:8000/api/device/my-router/send_command" \
  -H "X-API-Key: your-generated-key-here" \
  -H "Content-Type: application/json" \
  -d '{
    "command": "show version",
    "username": "your-username",
    "password": "your-password",
    "wait": true
  }'
```

Replace:
- `your-generated-key-here` with your API key
- `my-router` with your device name from inventory
- `your-username` with your device username
- `your-password` with your device password

You should see JSON output with the command results!

**How it works:** The `username` and `password` fields in the request body provide inline credentials, so you don't need a credential store for this quick start.

## What You Get

With this minimal setup:

**Included:**

- Execute commands on network devices
- Basic TextFSM parsing available - [Details here](parsing.md)
- Redis-backed job queueing
- API key authentication (primitive, still probably winding up on your disk somewhere, so not great)
- Pure YAML configuration (no `.env` files)
- Uses published Docker images (no building from source)

**Missing / Limitations:**

- No external inventory integration (NetBox/Nautobot/SolarWinds)
- Credentials passed in request body (not securely stored) - for a marginal improvement, see [YAML Credentials](yaml-credentials.md)
- No Vault or credential store
- No Redis TLS encryption
- No monitoring (Prometheus/Grafana)


## Common Issues 
No idea! You tell me!

## Next Steps

This setup is good enough for:  

- A basic smoke test of Tom itself
- Not much else, I think

**For a more practically useful setup**, see [Getting Started Sensibly](getting-started.md) which adds:

- Vault integration for secure credential storage
- Redis TLS encryption
- Better configuration practices
- Production deployment guidance
