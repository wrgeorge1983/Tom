# Sensible Setup Configuration

This directory contains a curated, working configuration for getting Tom Smykowski running with a more complete setup.

## What's Included

- `docker-compose.yml` - Full stack: controller, workers, Redis (TLS), Vault
- `tom_controller_config.yaml` - Controller configuration
- `inventory/inventory.yml` - Device inventory template
- `inventory/creds.yml` - YAML credential store (not recommended, see below)

## What's Different from Quick Start

| Feature | Quick Start | Sensible |
|---------|-------------|----------|
| Redis | Plain, no TLS | TLS enabled |
| Credentials | Inline in API calls | Vault |
| Workers | 3 replicas | 3 replicas |

## Usage

See the [Getting Started Sensibly](../docs/docs/real/getting-started.md) guide for complete instructions.

Quick version:

```bash
cd sensible-configs

# Generate and set your API key in tom_controller_config.yaml
python3 -c "import secrets; print(secrets.token_urlsafe(32))"

# Edit inventory/inventory.yml with your devices

# Start services
docker compose up

# In another terminal, store credentials in Vault (from repo root)
cd ..
uv run credload.py put lab_creds  # Prompts for username/password

# Test
curl -X POST "http://localhost:8000/device/router1/send_command" \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{"command": "show version", "wait": true}'
```

## Credentials

Credentials are stored in Vault and referenced by `credential_id` in inventory.

Use the included `credload.py` script (no vault CLI needed):

```bash
# From repo root
uv run credload.py put lab_creds              # Interactive
uv run credload.py put lab_creds -u admin -p secret  # Non-interactive
uv run credload.py list                       # List credentials
uv run credload.py get lab_creds              # View credential
```

If you really want to store credentials unencrypted on disk, see [YAML Credentials](../docs/docs/real/yaml-credentials.md).

## Security Notes

This setup is for **development and testing**. For production:

- Use Vault in production mode (not dev mode)
- Use proper TLS certificates for Redis
- Generate strong API keys
- Consider JWT/OAuth instead of API keys
