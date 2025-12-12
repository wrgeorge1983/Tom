# Vault Credential Store

Store credentials securely in HashiCorp Vault.

## Configuration

Set the credential plugin to `vault` in your worker config:

```yaml
# tom_worker_config.yaml
credential_plugin: "vault"

plugin_vault_url: "https://vault.example.com:8200"
plugin_vault_verify_ssl: true
plugin_vault_credential_path_prefix: "credentials"

# Authentication - choose ONE method:

# Option 1: Token (development only)
plugin_vault_token: "hvs.xxxxxxxxxxxxx"

# Option 2: AppRole (recommended for production)
plugin_vault_role_id: "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
plugin_vault_secret_id: "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
```

Or via environment variables:

```bash
TOM_WORKER_CREDENTIAL_PLUGIN=vault
TOM_WORKER_PLUGIN_VAULT_URL=https://vault.example.com:8200
TOM_WORKER_PLUGIN_VAULT_TOKEN=hvs.xxxxxxxxxxxxx
# or for AppRole:
TOM_WORKER_PLUGIN_VAULT_ROLE_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
TOM_WORKER_PLUGIN_VAULT_SECRET_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

## Vault Secret Structure

Credentials are stored in Vault's KV v2 secrets engine at:

```
secret/data/{credential_path_prefix}/{credential_id}
```

With the default `credential_path_prefix` of `credentials`, a credential named `lab_creds` would be at:

```
secret/data/credentials/lab_creds
```

Each secret must contain `username` and `password` keys:

```json
{
  "username": "admin",
  "password": "your-password"
}
```

## Using credload.py

The included `credload.py` script simplifies credential management:

```bash
# Store a credential (interactive password prompt)
uv run credload.py put lab_creds -u admin

# Store with password on command line
uv run credload.py put lab_creds -u admin -p your-password

# List all credentials
uv run credload.py list

# View a credential (password masked)
uv run credload.py get lab_creds

# Delete a credential
uv run credload.py delete lab_creds
```

## Authentication Methods

### Token Authentication

Simple but less secure. Use only for development.

```yaml
plugin_vault_token: "hvs.xxxxxxxxxxxxx"
```

### AppRole Authentication

Recommended for production. Create an AppRole in Vault with appropriate policies, then configure:

```yaml
plugin_vault_role_id: "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
plugin_vault_secret_id: "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
```

## Settings Reference

| Setting | Env Var | Required | Default |
|---------|---------|----------|---------|
| `plugin_vault_url` | `TOM_WORKER_PLUGIN_VAULT_URL` | Yes | - |
| `plugin_vault_token` | `TOM_WORKER_PLUGIN_VAULT_TOKEN` | * | `""` |
| `plugin_vault_role_id` | `TOM_WORKER_PLUGIN_VAULT_ROLE_ID` | * | `""` |
| `plugin_vault_secret_id` | `TOM_WORKER_PLUGIN_VAULT_SECRET_ID` | * | `""` |
| `plugin_vault_verify_ssl` | `TOM_WORKER_PLUGIN_VAULT_VERIFY_SSL` | No | `true` |
| `plugin_vault_credential_path_prefix` | `TOM_WORKER_PLUGIN_VAULT_CREDENTIAL_PATH_PREFIX` | No | `"credentials"` |

\* Either `token` OR both `role_id` and `secret_id` are required.
