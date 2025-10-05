# OAuth Token Recordings

This directory contains recorded OAuth interactions for testing.

## Purpose

These recordings allow us to test OAuth/JWT validation **without**:
- Live credentials in CI
- Hitting real provider APIs
- Token expiration issues
- Network dependencies

## Recording Structure

Each recording is a directory named `{provider}_{token_type}`:

```
google_id_token/
├── token.txt                    # The actual JWT string
├── discovery_request.json       # OIDC discovery request
├── discovery_response.json      # OIDC discovery document
├── jwks_request.json           # JWKS fetch request
├── jwks_response.json          # JWKS keys at recording time
├── decoded_claims.json         # Expected decoded claims
└── metadata.json               # Recording metadata
```

## Creating Recordings

To create or update a recording:

```bash
# Set environment variables
export GOOGLE_CLIENT_ID="your-id.apps.googleusercontent.com"
export GOOGLE_CLIENT_SECRET="your-secret"

# Run recording script (opens browser for OAuth)
python scripts/record_oauth_token.py google

# For access token instead of ID token
python scripts/record_oauth_token.py google --token-type access_token
```

## Available Recordings

- `google_id_token` - Google OAuth ID token (JWT, can validate)
- `google_access_token` - Google access token (opaque, cannot validate)
- `duo_id_token` - Duo ID token (JWT, can validate)
- `duo_access_token` - Duo access token (JWT, can validate)

## When to Re-record

Re-record when:
- Tokens expire (~1 hour typically)
- Provider rotates JWKS keys
- Provider changes discovery document
- Adding a new provider
- Testing configuration changes

## Metadata Format

```json
{
  "provider": "google",
  "token_type": "id_token",
  "recorded_at": "2025-10-03T14:30:00Z",
  "validation_time": 1696345800.0,
  "client_id": "123456.apps.googleusercontent.com",
  "expires_at": 1696349400,
  "requires_client_secret": true,
  "is_jwt": true,
  "notes": "Provider-specific quirks and requirements"
}
```

## Security Note

**Tokens in recordings are real but expired.** They cannot be used to access APIs but do contain real user data. Do not commit recordings with:
- Personally identifiable information (if sensitive)
- Tokens from production systems
- Long-lived tokens

Use test accounts and development OAuth apps for recordings.
