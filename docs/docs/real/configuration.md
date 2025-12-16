# Configuration

Tom services are configured via YAML files and environment variables.

## Config Files

| Service | Default File | Env Var Override |
|---------|--------------|------------------|
| Controller | `tom_controller_config.yaml` | `TOM_CONFIG_FILE` |
| Worker | `tom_worker_config.yaml` | `TOM_WORKER_CONFIG_FILE` |

Example configs are in the repo root: `tom_controller_config.example.yaml` and `tom_worker_config.example.yaml`.

## Precedence

Settings are loaded in this order (highest priority first):

1. Environment variables
2. YAML config file
3. Default values

## Environment Variables

Environment variables use prefixed names:

| Service | Prefix | Example |
|---------|--------|---------|
| Controller | `TOM_` | `TOM_LOG_LEVEL=debug` |
| Worker | `TOM_WORKER_` | `TOM_WORKER_LOG_LEVEL=debug` |

Plugin settings use an additional prefix:

```bash
# Controller inventory plugins
TOM_PLUGIN_YAML_INVENTORY_FILE=inventory.yml
TOM_PLUGIN_SOLARWINDS_HOST=swis.example.com

# Worker credential plugins
TOM_WORKER_PLUGIN_VAULT_URL=http://vault:8200
TOM_WORKER_PLUGIN_YAML_CREDENTIAL_FILE=creds.yml
```

## Plugin Settings

Both controller and worker use plugin systems. Plugin-specific settings use the pattern:

- YAML: `plugin_<name>_<setting>`
- Env: `TOM_[WORKER_]PLUGIN_<NAME>_<SETTING>`

See individual plugin documentation for available settings:

**Inventory plugins (controller):**

- [YAML Inventory](inventory-yaml.md)
- [NetBox](inventory-netbox.md)
- [Nautobot](inventory-nautobot.md)
- [SolarWinds](inventory-solarwinds.md)

**Credential plugins (worker):**

- [Vault](vault-credentials.md)
- [YAML](yaml-credentials.md)

## Validating Configuration

Each service includes a validator that checks config files for typos and unknown keys. The validators live in their respective packages because they need access to plugin-specific settings.

```bash
# Validate worker config (from services/worker directory)
uv run tom-worker-validate /path/to/tom_worker_config.yaml

# Validate controller config (from services/controller directory)
uv run tom-controller-validate /path/to/tom_controller_config.yaml
```

### Example Output

```
Tom Worker Configuration Validator
Config file: tom_worker_config.yaml

Validating: tom_worker_config.yaml
============================================================

WARNINGS:
  - Unknown key 'plugin_valut_url' - did you mean 'plugin_vault_url'?
  - Unknown key 'redishost' - did you mean 'redis_host'?

UNKNOWN KEYS (will be ignored):
  - plugin_valut_url
  - redishost

LOADED VALUES:
  credential_plugin: 'vault'
  log_level: 'info'
  plugin_vault_url: 'http://localhost:8200'
  redis_host: 'localhost'

RESULT: VALID (with warnings)
```

The validators detect:

- **Unknown keys** with fuzzy-match suggestions for typos
- **Unused plugin settings** (e.g., YAML plugin settings when Vault is selected)
- **Missing required values** for the selected plugin

## Common Settings

### Controller

```yaml
# tom_controller_config.yaml

log_level: "info"              # debug, info, warning, error
host: "0.0.0.0"
port: 8000

# Redis
redis_host: "localhost"
redis_port: 6379

# Inventory
inventory_type: "yaml"         # yaml, netbox, nautobot, solarwinds

# Authentication
auth_mode: "api_key"           # none, api_key, jwt, hybrid
api_keys: ["your-key:admin"]

# Caching
cache_enabled: true
cache_default_ttl: 300
```

### Worker

```yaml
# tom_worker_config.yaml

log_level: "info"
project_root: "."

# Redis
redis_host: "localhost"
redis_port: 6379

# Credentials
credential_plugin: "vault"     # vault (recommended), yaml
```

See the example config files for all available options.

## Adapters and Drivers

Tom supports two network automation libraries (adapters): **Netmiko** and **Scrapli**. See the [Adapters and Drivers Reference](drivers.md) for the full list of supported platforms.
