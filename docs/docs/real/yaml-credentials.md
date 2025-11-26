# Using YAML Credential Store

If you really want to store credentials unencrypted on your disk, here's how to use YAML as a credential source.

**This is NOT recommended for anything beyond local testing.** Use Vault instead.

## Configuration

Edit your docker-compose worker environment to use YAML credentials:

```yaml
environment:
  TOM_WORKER_CREDENTIAL_STORE: yaml
  TOM_WORKER_CREDENTIAL_FILE: inventory/creds.yml
```

If using the sensible-configs setup, comment out the Vault settings and uncomment the YAML ones.

## Credential File Format

Create a YAML file with your credentials:

```yaml
# inventory/creds.yml

lab_creds:
  username: admin
  password: your-password

production_creds:
  username: netops
  password: different-password

cisco_tacacs:
  username: tacacs_user
  password: tacacs_secret
```

Each top-level key is a `credential_id` that you reference in your inventory:

```yaml
# inventory/inventory.yml

router1:
  host: "192.168.1.1"
  adapter: "netmiko"
  adapter_driver: "cisco_ios"
  credential_id: "lab_creds"  # References the YAML credential
```

## Why You Shouldn't Use This

1. **Plaintext passwords** - Anyone with file access can read them
2. **Version control risk** - Easy to accidentally commit credentials
3. **No audit trail** - No logging of credential access
4. **No rotation support** - Manual updates required

## When It Might Be Acceptable

- Local development with test credentials
- Isolated lab environments
- Quick testing before setting up Vault

For anything else, use [Vault](getting-started.md#5-store-credentials-in-vault).
