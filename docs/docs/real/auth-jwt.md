# JWT/OAuth Authentication

Tom can validate JWT (JSON Web Token) tokens from OAuth providers, enabling SSO integration for interactive users. Tom validates tokens but doesn't issue them - clients obtain tokens from their OAuth provider and present them to Tom.

## When to Use

- Interactive users (humans)
- SSO integration with existing identity provider
- User-level audit logging
- When you need granular access control by user/domain

## Supported Providers

| Provider | Status | Notes |
|----------|--------|-------|
| Duo Security | Tested | ID tokens and access tokens |
| Google OAuth | Tested | ID tokens only (access tokens are opaque) |
| Microsoft Entra ID | Tested | Full OIDC support |

Other OIDC-compliant providers should work with minimal configuration.

## How It Works

```mermaid
sequenceDiagram
    participant Client
    participant Provider as OAuth Provider
    participant Tom

    Client->>Provider: Authenticate (browser/CLI)
    Provider-->>Client: JWT token
    Client->>Tom: API request + Bearer token
    Tom->>Provider: Fetch JWKS (public keys)
    Provider-->>Tom: JWKS
    Note over Tom: Validate token signature,<br/>check claims & authorization
    Tom-->>Client: Response
```

1. Client authenticates with OAuth provider and receives a JWT
2. Client sends API request to Tom with `Authorization: Bearer <token>`
3. Tom fetches the provider's public keys (JWKS) to validate the token signature
4. Tom checks authorization rules (allowed users/domains)
5. Request proceeds if valid

## Configuration

### Basic Setup

```yaml
# tom_controller_config.yaml
auth_mode: jwt

jwt_providers:
  - name: google           # Unique identifier for this provider instance
    type: google           # Provider type: duo, google, or entra
    enabled: true
    client_id: "your-client-id.apps.googleusercontent.com"
    discovery_url: "https://accounts.google.com/.well-known/openid-configuration"
```

### Multiple Providers

```yaml
jwt_providers:
  - name: google
    type: google
    enabled: true
    client_id: "google-client-id"
    discovery_url: "https://accounts.google.com/.well-known/openid-configuration"

  - name: entra
    type: entra
    enabled: true
    client_id: "entra-client-id"
    tenant_id: "your-tenant-id"
    discovery_url: "https://login.microsoftonline.com/your-tenant-id/v2.0/.well-known/openid-configuration"

  - name: duo
    type: duo
    enabled: false  # Disabled
    client_id: "duo-client-id"
    discovery_url: "https://your-tenant.duosecurity.com/.well-known/openid-configuration"
```

Tom tries each enabled provider in order until one validates the token.

### Multiple Providers of Same Type

You can configure multiple providers of the same type with different names. This is useful for service-to-service authentication where different services have different OAuth clients:

```yaml
jwt_providers:
  # Accept tokens from your primary app
  - name: duo-primary
    type: duo
    client_id: "PRIMARY_CLIENT_ID"
    discovery_url: "https://sso.example.com/oidc/PRIMARY_CLIENT_ID/.well-known/openid-configuration"

  # Accept tokens from an internal service
  - name: duo-internal-service
    type: duo
    client_id: "INTERNAL_SERVICE_CLIENT_ID"
    discovery_url: "https://sso.example.com/oidc/INTERNAL_SERVICE_CLIENT_ID/.well-known/openid-configuration"
    audience:
      - "PRIMARY_CLIENT_ID"        # Accept tokens intended for primary app
      - "INTERNAL_SERVICE_CLIENT_ID"
```

### Provider Options

| Option | Required | Default | Description |
|--------|----------|---------|-------------|
| `name` | Yes | - | Unique identifier for this provider instance |
| `type` | Yes | - | Provider type: `duo`, `google`, or `entra` |
| `enabled` | No | `true` | Enable/disable this provider |
| `client_id` | Yes | - | OAuth client ID |
| `discovery_url` | Yes | - | OIDC discovery endpoint |
| `audience` | No | `client_id` | Expected token audience (string or list) |
| `tenant_id` | No | - | Microsoft Entra tenant ID |
| `leeway_seconds` | No | `30` | Clock skew tolerance |

## Authorization

After validating the JWT, Tom checks if the user is authorized:

```yaml
# Allow specific users (exact match, case-insensitive)
allowed_users:
  - alice@example.com
  - bob@company.com
  - service.account

# Allow by email domain
allowed_domains:
  - example.com
  - subsidiary.com

# Allow by regex pattern
allowed_user_regex:
  - '^netops-.*@example\.com$'
  - '^[a-z]+\.admin@example\.com$'
```

### Authorization Logic

1. Check `allowed_users` - exact match on email/username
2. Check `allowed_domains` - domain extracted from email
3. Check `allowed_user_regex` - pattern match

Any match grants access (OR logic). If all three lists are empty, any valid JWT is authorized (which would be terrible
in production! Do you REALLY want 'any authenticated google user' to login? Probably not!).

### User Identifier

The user identifier depends on the provider:

| Provider | Identifier Source |
|----------|-------------------|
| Google | `email` or `sub` |
| Duo | `preferred_username` or `email` or `sub` |
| Entra | `preferred_username` or `upn` or `email` or `sub` |

## Usage

Include the JWT in the Authorization header:

```bash
curl -H "Authorization: Bearer eyJhbGciOiJSUzI1NiIs..." \
  "http://localhost:8000/api/device/router1/send_command?command=show+version&wait=true"
```

## Provider-Specific Setup

### Google OAuth

1. Create project in [Google Cloud Console](https://console.cloud.google.com)
2. Enable OAuth consent screen
3. Create OAuth 2.0 Client ID (Web application or Desktop)
4. Note the Client ID

```yaml
jwt_providers:
  - name: google
    type: google
    enabled: true
    client_id: "123456789-abc.apps.googleusercontent.com"
    discovery_url: "https://accounts.google.com/.well-known/openid-configuration"
```

**Note**: Google access tokens are opaque. Use ID tokens for Tom authentication.

### Microsoft Entra ID

1. Register application in [Azure Portal](https://portal.azure.com) > App Registrations
2. Note the Application (client) ID and Directory (tenant) ID
3. Configure redirect URIs as needed

```yaml
jwt_providers:
  - name: entra
    type: entra
    enabled: true
    client_id: "your-application-id"
    tenant_id: "your-tenant-id"
    discovery_url: "https://login.microsoftonline.com/your-tenant-id/v2.0/.well-known/openid-configuration"
```

### Duo Security

1. Create OIDC application in Duo Admin Panel
2. Note the Client ID and API hostname

```yaml
jwt_providers:
  - name: duo
    type: duo
    enabled: true
    client_id: "your-duo-client-id"
    discovery_url: "https://your-tenant.duosecurity.com/.well-known/openid-configuration"
```

## CLI Client

For an example of oAuth for command-line access, see [tomclient](https://github.com/wrgeorge1983/tomclient) - a reference implementation that handles OAuth PKCE flow for CLI authentication.

```bash
# Authenticate with OAuth provider
tomclient auth login
# oAuth flow runs in browser

# Make API calls (token handled automatically)
tomclient device router1 "show version"
```

## Security Settings

### HTTPS Enforcement

```yaml
jwt_require_https: true  # Default: true
```

Keep enabled in production. Only disable for local development.

### Token Leeway

Allow clock skew between Tom and the OAuth provider:

```yaml
jwt_providers:
  - name: google
    type: google
    leeway_seconds: 30  # Default
```

## Testing

Tom includes a test page for OAuth flow debugging:

```yaml
oauth_test_enabled: true  # Enable test endpoints (dev only)

jwt_providers:
  - name: google
    type: google
    oauth_test_client_secret: "your-client-secret"  # Only for test flow
    oauth_test_scopes: ["openid", "email", "profile"]
```

Access at `http://localhost:8000/static/oauth-test.html`

**Warning**: Never enable `oauth_test_enabled` in production.



## Debug Endpoint

Check authentication status:

```bash
curl -H "Authorization: Bearer eyJ..." \
  "http://localhost:8000/api/auth/debug"
```

Returns:

```json
{
  "method": "jwt",
  "user": "alice@example.com",
  "provider": "google",
  "all_claims": { ... },
  "custom_claims": { ... }
}
```

The `custom_claims` field filters out standard JWT claims (iss, sub, aud, exp, etc.) to show only provider-specific claims.
