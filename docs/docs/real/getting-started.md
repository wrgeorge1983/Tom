# Getting Started Sensibly

This guide will help you get Tom Smykowski up and running with a more complete setup including Vault for credential storage, Redis with TLS, and monitoring.

## This is still NOT a production setup

In particular, the Vault setup here uses dev mode. If you put live credentials in there, don't tell your security people I told you it was okay!

(Though in reality it will still be safer than plaintext on your hard drive...)

## It IS a pretty reasonable setup for a lab and getting a feel for what Tom can do

## Prerequisites

- Docker and Docker Compose
- Network devices accessible via SSH
- Valid credentials for your network devices

## 1. Clone and Enter Sensible Directory

```bash
git clone https://github.com/wrgeorge1983/tom.git
cd tom/sensible-configs
```

## 2. Generate and Configure Your API Key

Generate a secure API key:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Edit `tom_controller_config.yaml` and replace the placeholder:

```yaml
api_keys: ["YOUR-GENERATED-KEY-HERE:admin"]
```

## 3. Configure Your Inventory

Edit `inventory/inventory.yml` with your devices:

```yaml
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
```

**Required fields:**

- `host` - IP address or hostname
- `adapter` - `netmiko` or `scrapli`
- `adapter_driver` - Platform type (e.g., `cisco_ios`, `cisco_iosxe`, `arista_eos`)
- `credential_id` - Reference to credentials in Vault (see next step)

## 4. Start Services

```bash
docker compose up
```

**Note:** If you already have images tagged `latest` locally, Docker won't automatically pull newer versions. Run `docker compose pull` to get updates.

This starts:

- **Controller** - API server on port 8000
- **Worker** (3 replicas) - Executes commands on devices
- **Redis** - Job queue and caching (with TLS on port 6380)
- **Vault** - Credential storage (dev mode on port 8200)

Wait for services to start, then open a new terminal for the next steps.

## 5. Store Credentials in Vault

Use the included `credload.py` script (no need to install the vault CLI):

```bash
cd tom

# Interactive - prompts for username and password securely
uv run credload.py put lab_creds

# Or provide on command line
uv run credload.py put lab_creds -u admin -p your-device-password
```

The `credential_id` in your inventory (`lab_creds`) must match what you store in Vault.

Other useful commands:

```bash
uv run credload.py list              # List all stored credentials
uv run credload.py get lab_creds     # View a credential (password masked)
uv run credload.py delete lab_creds  # Delete a credential
```

## 6. Test the API

```bash
curl -X POST "http://localhost:8000/device/router1/send_command" \
  -H "X-API-Key: YOUR-GENERATED-KEY-HERE" \
  -H "Content-Type: application/json" \
  -d '{
    "command": "show version",
    "wait": true
  }'
```

You should see JSON output with the command results.

If you really want to store credentials unencrypted on your disk, see [YAML Credentials](yaml-credentials.md).

## Configuration Approach

Tom supports both YAML config files and environment variables, with precedence: **environment variables > config file > defaults**.

**Recommended approach:**

- **Use YAML config files** for most settings - readable, supports comments, version-controllable
- **Use environment variables** only for:
    - Secrets (Vault tokens)
    - Container runtime overrides
    - Values that differ between environments

### Controller Configuration

The controller config lives in `tom_controller_config.yaml`. See `tom_controller_config.example.yaml` in the repo root for all available options.

### Worker Configuration

Worker settings are in docker-compose environment variables. The key ones:

- `TOM_WORKER_CREDENTIAL_STORE` - `vault` or `yaml`
- `TOM_WORKER_VAULT_URL` / `TOM_WORKER_VAULT_TOKEN` - Vault connection
- `TOM_WORKER_CREDENTIAL_FILE` - Path to YAML creds (if using yaml store)

## Troubleshooting

### Services Won't Start

Check logs in the terminal running docker compose, or:

```bash
docker compose logs controller
docker compose logs worker
```

### Cannot Connect to Devices

1. Verify network connectivity:

    ```bash
    docker compose exec worker ping 192.168.1.1
    ```

2. Check credentials in Vault:

    ```bash
    vault kv get secret/lab_creds
    ```

3. Review worker logs for errors

### API Returns 401 Unauthorized

- Verify API key matches `tom_controller_config.yaml`
- Ensure `X-API-Key` header is being sent
- Check controller logs

## Production Considerations

Before deploying to production:

1. **Vault** - Use production mode with proper unsealing
2. **Redis** - Use proper TLS certificates
3. **API Keys** - Generate strong keys; consider JWT/OAuth
4. **Network** - Place Tom in appropriate network zones
5. **Monitoring** - Configure alerting in Prometheus/Grafana

## Next Steps

- [Parsing](parsing.md) - Parse command output with TextFSM/TTP templates
- Configure external inventory sources (NetBox, Nautobot, SolarWinds)
- Set up JWT/OAuth authentication
