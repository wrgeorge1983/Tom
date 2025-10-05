# Authorization Implementation - TODO

## Current State
- **Status**: Authenticated = Authorized
- Any valid JWT from any configured provider gets full access
- No filtering on user identity, email, or claims
- User identifier extracted only for logging purposes

## Decision: Hybrid Authorization Model

Implement three authorization mechanisms (all optional, per-provider):

### 1. Exact Email Allowlist
```yaml
jwt_providers:
  - name: google
    discovery_url: "..."
    client_id: "..."
    allowed_emails:
      - "admin@company.com"
      - "ops@company.com"
```
- Simple list of allowed email addresses
- Exact string matching
- Good for small teams or specific service accounts

### 2. Email Pattern (Regex)
```yaml
jwt_providers:
  - name: google
    discovery_url: "..."
    client_id: "..."
    allowed_email_pattern: ".*@acme\\.com$"
```
- Regex pattern matching against `email` claim
- Good for "anyone from our domain" policies
- Most common use case (90% of authorization needs)

### 3. Arbitrary Claim Matching
```yaml
jwt_providers:
  - name: google
    discovery_url: "..."
    client_id: "..."
    required_claims:
      hd: "acme.com"           # Google Workspace hosted domain
      email_verified: true      # Email must be verified
      
  - name: entra
    discovery_url: "..."
    client_id: "..."
    required_claims:
      groups: ["IT-Admins"]     # Entra groups claim (array matching TBD)
```
- Match any claim in the JWT
- Supports provider-specific claims (Google `hd`, Entra `groups`, etc.)
- Most flexible for complex policies

## Implementation Details

### Config Schema (`config.py`)
```python
class JWTProviderConfig(BaseModel):
    # ... existing fields ...
    
    # Authorization (optional - if not set, any valid JWT allowed)
    allowed_emails: Optional[list[str]] = None
    allowed_email_pattern: Optional[str] = None
    required_claims: Optional[dict[str, Any]] = None
```

### Validation Logic (`jwt_validator.py`)
Add to `_validate_claims()` method:
1. Check `allowed_emails` if configured (exact match)
2. Check `allowed_email_pattern` if configured (regex match)
3. Check `required_claims` if configured (key-value match)
4. Raise `JWTInvalidClaimsError` on authorization failure

### Error Handling
- Authorization failures should return **403 Forbidden** (not 401 Unauthorized)
- 401 = authentication failed (bad/expired token)
- 403 = authenticated but not authorized (valid token, not permitted)

### Combining Rules
When multiple rules are configured on the same provider:
- **ALL** rules must pass (AND logic)
- Example: `allowed_email_pattern` AND `required_claims` both checked

### Default Behavior
- **No rules configured**: Allow all valid JWTs (current behavior)
- Maintains backward compatibility
- Explicit opt-in to authorization

## Open Questions

### 1. Array Claim Matching
For claims like `groups: ["IT-Admins", "Users"]`:
- Exact match: JWT must have exactly this array?
- Contains: JWT array must contain these values?
- **Recommendation**: "Contains" semantics (more useful)

### 2. Global vs Per-Provider
Should there be global authorization rules that apply to all providers?
```yaml
# Global (applies to all providers)
authorization:
  allowed_email_pattern: ".*@company\\.com$"

# Per-provider overrides
jwt_providers:
  - name: google
    allowed_emails: ["external-contractor@example.com"]  # Exception
```
**Recommendation**: Start with per-provider only, add global later if needed

### 3. Multiple Patterns
Should we support multiple email patterns?
```yaml
allowed_email_patterns:
  - ".*@company\\.com$"
  - ".*@subsidiary\\.com$"
```
**Recommendation**: Yes, OR logic between patterns

### 4. Case Sensitivity
Should email matching be case-insensitive?
```yaml
allowed_emails: ["Admin@Company.com"]  # matches admin@company.com?
```
**Recommendation**: Yes, emails are case-insensitive per RFC 5321

## Example Use Cases

### Startup (Single Domain)
```yaml
- name: google
  discovery_url: "..."
  client_id: "..."
  allowed_email_pattern: ".*@startup\\.com$"
```

### Enterprise (Specific Group)
```yaml
- name: entra
  discovery_url: "..."
  client_id: "..."
  required_claims:
    groups: ["Network-Admins"]
  allowed_email_pattern: ".*@enterprise\\.com$"
```

### Multi-Tenant SaaS (Verified Emails Only)
```yaml
- name: google
  discovery_url: "..."
  client_id: "..."
  required_claims:
    email_verified: true
```

### Contractor Access (Specific Users)
```yaml
- name: duo
  discovery_url: "..."
  client_id: "..."
  allowed_emails:
    - "contractor1@external.com"
    - "contractor2@external.com"
```

## Testing Checklist

When implementing:
- [ ] Test email exact match (case insensitive)
- [ ] Test email pattern with valid regex
- [ ] Test email pattern with invalid regex (fail gracefully)
- [ ] Test missing email claim
- [ ] Test required_claims with simple values
- [ ] Test required_claims with missing claims
- [ ] Test required_claims with array values (contains logic)
- [ ] Test combining multiple authorization rules (AND logic)
- [ ] Test with no authorization rules (allow all)
- [ ] Verify 403 vs 401 error codes
- [ ] Test error messages are clear and actionable
- [ ] Test with all three providers (Duo, Google, Entra)

## Priority
**Medium** - Current "authenticated = authorized" works for many use cases, but authorization is important for production deployments with multiple users.

## Related Files
- `services/controller/src/tom_controller/config.py` - Add authorization fields
- `services/controller/src/tom_controller/auth/jwt_validator.py` - Implement validation logic
- `services/controller/src/tom_controller/api/api.py` - Update error handling (403 vs 401)
- `services/controller/src/tom_controller/exceptions.py` - Add `JWTAuthorizationError` exception?
- `tom_config.jwt.example.yaml` - Add authorization examples
- `docs/oauth-implementation.md` - Update "Authenticated = Authorized" section
