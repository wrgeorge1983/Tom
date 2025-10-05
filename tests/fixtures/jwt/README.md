# JWT Test Fixtures

This directory contains recorded JWT tokens from real OAuth providers used for testing Tom's validation logic.

## Security & Privacy

**⚠️ Fixtures are `.gitignore`d for privacy reasons:**
- JWTs contain real user information (email, name, user IDs)
- Even though tokens expire, we don't commit PII to git history
- Each developer generates their own fixtures

## Generating Test Fixtures

### Prerequisites

1. **Set up OAuth test accounts** for each provider you want to test:
   - Google: Create a test Google account
   - Duo: Create a test Duo account  
   - Microsoft Entra: Create a test Entra user
   
2. **Configure Tom with your OAuth providers** in `tom_controller_config.yaml`:
   ```yaml
   auth_mode: jwt
   jwt_providers:
     - name: google
       enabled: true
       client_id: "your-test-client-id.apps.googleusercontent.com"
       discovery_url: "https://accounts.google.com/.well-known/openid-configuration"
   ```

### Recording Fixtures

1. **Enable test recording mode:**
   ```bash
   export TOM_ENABLE_TEST_RECORDING=true
   ```

2. **Start Tom:**
   ```bash
   cd services/controller
   uv run tom-controller
   ```

3. **Get a JWT from your provider:**
   
    * The only really tested / supported path right now is via `tomclient` cli. 
    * `tomclient auth login`
    * `tomclient auth record` 
      * this POSTs to the JWT recording endpoint

5. **Fixture is created:**
   ```
   tests/fixtures/jwt/{provider}_{valid|invalid}_{timestamp}.yaml
   ```

6. **Disable recording:**
   ```bash
   unset TOM_ENABLE_TEST_RECORDING
   ```

### Recording Invalid Tokens

To test error cases, you should be able to record:

**Expired tokens:** Wait for token to expire, then record it
**Tampered tokens:** Modify a JWT before recording (will be marked invalid)
**Wrong audience:** Use a token from different client_id

The recording endpoint automatically detects validity and saves appropriately.

## Fixture Format

Each fixture contains:

```yaml
description: "Recorded from live google token"
recorded_at: "2025-01-15T10:00:00Z"
provider: google
jwt: "eyJhbGci..."  # The actual JWT token

provider_config:    # Configuration used during validation
  name: google
  discovery_url: "https://accounts.google.com/.well-known/openid-configuration"
  client_id: "your-client-id.apps.googleusercontent.com"
  issuer: "https://accounts.google.com"
  jwks_uri: "https://www.googleapis.com/oauth2/v3/certs"
  audience: null
  leeway_seconds: 30

expected:
  valid: true
  user: "test-user@company.com"
  provider: google
  claims:             # All JWT claims
    iss: "https://accounts.google.com"
    sub: "1234567890"
    email: "test-user@company.com"
    email_verified: true
    aud: "your-client-id.apps.googleusercontent.com"
    iat: 1705315200
    exp: 1705318800
    # ... other claims

validation_time: "2025-01-15T10:00:00Z"  # When token was valid
expiration_time: "2025-01-15T11:00:00Z"  # When token expires
```

## Running Tests

Tests automatically discover all fixtures matching patterns:

```bash
# Run all JWT validation tests
cd services/controller
uv run pytest ../../tests/test_jwt_validation.py -v

# First run records VCR cassettes (JWKS/discovery HTTP calls)
uv run pytest --record-mode=once ../../tests/test_jwt_validation.py -v
```

**Note:** You need at least one fixture per provider for tests to run:
- `google_valid_*.yaml` - For Google tests
- `duo_valid_*.yaml` - For Duo tests
- `entra_valid_*.yaml` - For Entra tests

If fixtures are missing, tests will be skipped with a clear message.

## VCR Cassettes

HTTP interactions (OIDC discovery, JWKS fetch) are recorded separately in `tests/cassettes/`:
- These contain only public keys and provider metadata
- Safe to commit to git
- Created automatically on first test run

## Recommended Fixture Naming

- `{provider}_valid_{timestamp}.yaml` - Valid token from provider
- `{provider}_expired_{timestamp}.yaml` - Expired token
- `{provider}_invalid_signature_{timestamp}.yaml` - Tampered token
- `{provider}_invalid_aud_{timestamp}.yaml` - Wrong audience


## Security Notes

- **Never commit real user JWTs** - use dedicated test accounts
- **Fixtures are local-only** - regenerate per environment
- **Token expiration is not an issue** - tests always mock the time to what is recorded in the fixture
- **No secrets in JWTs** - they're bearer tokens, contain no passwords
- **Public keys safe** - JWKS/discovery responses are public, commit those

## Troubleshooting

**"No fixtures found, tests skipped"**
- Generate fixtures using steps above
- Ensure fixtures are in `tests/fixtures/jwt/`
- Check naming matches pattern (`google_valid_*.yaml`)

**"JWKS fetch failed"**
- Run with `--record-mode=once` to record cassettes
- Check network connectivity to OAuth providers
- Verify discovery URLs are correct

**"Token validation failed"**
- Verify provider config matches token issuer/audience
- Regenerate fixture with current config
