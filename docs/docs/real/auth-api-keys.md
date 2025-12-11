# API Key Authentication

API key authentication is the simplest way to secure Tom. Clients include a key in the request header, and Tom validates it against a configured list.

## When to Use

- Automated scripts and tools
- Service-to-service communication
- Simple setups without SSO requirements
- When you don't need user-level identity

## Configuration

### Enable API Key Auth

```yaml
# tom_controller_config.yaml
auth_mode: api_key

# Define API keys (format: "key:username")
api_keys:
  - "abc123secret:automation"
  - "xyz789token:monitoring"
```

Or via environment variable:

```bash
TOM_AUTH_MODE=api_key
TOM_API_KEYS='["abc123secret:automation", "xyz789token:monitoring"]'
```

### Key Format

Each key entry has the format `key:username`:

- **key**: The actual API key value (keep this secret)
- **username**: currently unused, but may be used in the future for user-level access control

```yaml
api_keys:
  - "my-secret-key-here:scriptuser"
  - "another-key:admin"
```

### Custom Header Name

By default, Tom looks for the `X-API-Key` header. You can change this:

```yaml
api_key_headers:
  - "X-API-Key"
  - "Authorization"  # Add multiple if needed
```

## Usage

Include the API key in the header:

```bash
curl -H "X-API-Key: abc123secret" \
  "http://localhost:8000/api/device/router1/send_command?command=show+version&wait=true"
```

## Generating Keys

Generate secure random keys:

```bash
# Python
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Example output: `Kx7Qm_vR3nL8Yp2Wz1Hs9Jc4Fb6Td0Xn5Mg`
