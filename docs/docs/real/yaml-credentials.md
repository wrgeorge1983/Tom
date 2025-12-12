# YAML Credential Store

Store credentials in a local YAML file.

**Not recommended for production.** Use [Vault](vault-credentials.md) instead.

## Configuration

Set the credential plugin to `yaml` in your worker config:

```yaml
# tom_worker_config.yaml
credential_plugin: "yaml"
plugin_yaml_credential_file: "inventory/creds.yml"
```

Or via environment variables:

```bash
TOM_WORKER_CREDENTIAL_PLUGIN=yaml
TOM_WORKER_PLUGIN_YAML_CREDENTIAL_FILE=inventory/creds.yml
```

## Credential File Format

```yaml
# inventory/creds.yml

lab_creds:
  username: admin
  password: your-password

production_creds:
  username: netops
  password: different-password
```

Each top-level key is a `credential_id` referenced in your inventory:

```yaml
# inventory/inventory.yml
router1:
  host: "192.168.1.1"
  adapter: "netmiko"
  adapter_driver: "cisco_ios"
  credential_id: "lab_creds"
```

## Why You Shouldn't Use This

- **Plaintext passwords** - Anyone with file access can read them
- **Version control risk** - Easy to accidentally commit credentials
- **No audit trail** - No logging of credential access
- **No rotation support** - Manual updates required

## When It's Acceptable

- Local development with test credentials
- Isolated lab environments
- Quick testing before setting up Vault
