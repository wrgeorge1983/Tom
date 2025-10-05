# Tom OAuth/JWT Testing

This directory contains tests for Tom's OAuth/OIDC JWT validation functionality.

## Philosophy

These tests focus on **contract validation** - ensuring we correctly interpret and validate JWTs from real OAuth providers. We use recorded fixtures (VCR-style) to:

1. Test against real JWTs from actual providers (Google, Duo, Entra)
2. Verify we extract the same claims consistently
3. Ensure provider-specific validation rules work correctly
4. Avoid mocking internal implementation details

## Structure

```
tests/
├── conftest.py                 # Pytest configuration and shared fixtures
├── test_jwt_validation.py      # JWT validation tests
├── fixtures/
│   └── jwt/                    # Recorded JWT fixtures
│       ├── google_valid_*.yaml
│       ├── duo_valid_*.yaml
│       └── entra_valid_*.yaml
└── cassettes/                  # VCR cassettes (HTTP recordings)
    ├── test_google_valid_token.yaml
    └── ...
```

## Recording JWT Fixtures

To record a JWT for testing:

1. **Enable test recording mode:**
   ```bash
   export TOM_ENABLE_TEST_RECORDING=true
   ```

2. **Start Tom:**
   ```bash
   cd services/controller
   uv run tom-controller
   ```

3. **Get a JWT from your provider** (via oauth-test.html or your app)

4. **Record it:**
   ```bash
   curl -X POST http://localhost:8020/api/dev/record-jwt \
     -H "Authorization: Bearer eyJhbGci..."
   ```

5. **Fixture saved to:** `tests/fixtures/jwt/{provider}_{valid|invalid}_{timestamp}.yaml`

6. **Disable recording:**
   ```bash
   unset TOM_ENABLE_TEST_RECORDING
   ```

## Running Tests

### Run all tests:
```bash
cd /home/willgeorge/projects/tom
uv run pytest
```

### Run only JWT validation tests:
```bash
uv run pytest -m jwt
```

### Run with verbose output:
```bash
uv run pytest -v
```

### Record new HTTP cassettes:
```bash
uv run pytest --record-mode=once
```

### Rewrite all cassettes:
```bash
uv run pytest --record-mode=rewrite
```

## What Gets Tested

### ✅ Contracts We Validate
- JWT signature verification (using real JWKS from providers)
- Claims extraction consistency (same token → same claims)
- User identifier extraction (claims → user)
- Provider-specific validation rules:
  - Google: `email` and `email_verified` claims
  - Entra: `tenant_id` matching
- Token expiration handling
- Issuer/provider matching

### ❌ What We Don't Test
- Crypto algorithm internals (trust python-jose)
- HTTP client behavior (trust httpx)
- Provider's token issuance process
- OAuth authorization flow (not Tom's responsibility)

## Fixture Format

Each JWT fixture contains:

```yaml
description: "Recorded from live google token"
recorded_at: "2025-01-15T10:00:00Z"
provider: google
jwt: "eyJhbGci..."  # The actual JWT token

provider_config:    # Config used during validation
  name: google
  discovery_url: "https://..."
  client_id: "..."
  issuer: "https://accounts.google.com"
  jwks_uri: "https://..."
  audience: null
  leeway_seconds: 30

expected:
  valid: true
  user: "user@company.com"
  provider: google
  claims:             # All extracted claims
    iss: "https://accounts.google.com"
    sub: "1234567890"
    email: "user@company.com"
    # ... all other claims

validation_time: "2025-01-15T10:00:00Z"  # When token was valid
expiration_time: "2025-01-15T11:00:00Z"  # When token expires
```

## VCR Cassettes

HTTP interactions (OIDC discovery, JWKS fetch) are recorded in cassettes:

- **First run:** Cassettes are created by making real HTTP calls
- **Subsequent runs:** Cassettes are replayed (no network calls)
- **Fast & deterministic:** Tests run offline once cassettes exist

### Cassette Format
```yaml
interactions:
- request:
    uri: https://accounts.google.com/.well-known/openid-configuration
    method: GET
  response:
    status: {code: 200}
    body: {string: '{"issuer":"https://accounts.google.com",...}'}
```

## Time Mocking

Tests use `freezegun` to freeze time during validation:

```python
with freeze_time(fixture["validation_time"]):
    claims = await validator.validate_token(fixture["jwt"])
```

This allows testing:
- Valid tokens (time = validation_time)
- Expired tokens (time > expiration_time)

## Adding New Tests

1. **Record a fixture** using `/dev/record-jwt` endpoint
2. **Run test with --record-mode=once** to create cassettes
3. **Verify test passes**
4. **Commit fixture + cassette** to git

Example:
```python
async def test_new_provider_token(self, load_jwt_fixture):
    fixture = load_jwt_fixture("newprovider_valid_123456.yaml")
    
    with freeze_time(fixture["validation_time"]):
        validator = get_jwt_validator(fixture["provider_config"])
        await validator._ensure_discovery()
        
        claims = await validator.validate_token(fixture["jwt"])
        
        assert claims["email"] == fixture["expected"]["claims"]["email"]
        
        await validator.close()
```

## CI/CD Integration

Tests are designed to run in CI:
- No network calls (cassettes replay)
- Fast execution (< 1 second per test)
- Deterministic results
- No environment setup needed

## Security Note

JWT fixtures contain real tokens from OAuth providers. These tokens:
- Are short-lived and expire naturally
- Are already sent to Tom during normal operation
- Don't contain sensitive data beyond user identity
- Can be `.gitignore`d if needed for extra security
