# Quick Start Configuration Bundle

This directory contains everything you need to get Tom Smykowski running quickly with minimal configuration.

## What's Included

- `docker-compose.yml` - Minimal compose file (controller, worker, redis only)
- `tom_controller_config.yaml` - Controller configuration (YAML)
- `inventory/inventory.yml` - Device inventory template (YAML)

**All configuration is in YAML files** - no `.env` files needed. This is the familiar pattern for network automation folks.

## What's NOT Included (vs main docker-compose)

- HashiCorp Vault
- Prometheus
- Grafana  
- Documentation server
- Credential store (uses inline credentials only)
- Environment variable files
- Redis TLS (uses plain Redis for simplicity)
- Source code builds (uses published ghcr.io images)

This keeps the setup minimal and fast. For a more complete setup, see the main `docker-compose.yml` at the repository root.

## Usage

See the [Getting Started Fast](../docs/docs/real/getting-started-FAST.md) guide for complete instructions.

Quick version:
```bash
cd quickstart-configs
# Edit tom_controller_config.yaml with your API key
# Edit inventory/inventory.yml with your devices
docker compose up
```

## Security Notes

**This configuration is for QUICK SETUP and TESTING only.**

- API keys in plain text YAML files
- Device credentials inline in inventory YAML
- No secrets management
- Suitable for lab/dev environments only

For production, see [Getting Started Sensibly](../docs/docs/real/getting-started.md).
