# Authentication

Tom supports multiple authentication methods:

| Mode | Use Case | Documentation |
|------|----------|---------------|
| `none` | Development/testing only | No auth required |
| `api_key` | Service accounts, scripts | [API Keys](auth-api-keys.md) |
| `jwt` | Interactive users, SSO | [JWT/OAuth](auth-jwt.md) |
| `hybrid` | Both API keys and JWT | Accepts either method |

## Configuration

```yaml
# tom_controller_config.yaml
auth_mode: api_key  # Options: none, api_key, jwt, hybrid
```

## Hybrid Mode

Tries API key first, then JWT. Useful when you have both automated systems and interactive users.

## Authorization

API keys have full access. JWT users can be restricted by email - see [JWT/OAuth](auth-jwt.md#authorization) for details.

## Security

- Never use `auth_mode: none` in production
- Use HTTPS (Tom enforces this for JWT by default)
- Deploy behind a reverse proxy for TLS termination, rate limiting, and request logging
