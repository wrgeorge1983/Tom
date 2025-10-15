# Authorization Implementation - ✅ COMPLETED

## Current State
- **Status**: ✅ Email-based authorization implemented
- Three authorization mechanisms available: exact users, domains, and regex patterns
- All configurable via YAML config or environment variables
- Precedence: allowed_users → allowed_domains → allowed_user_regex
- If all lists are empty, any valid JWT is authorized (backward compatible)

## Implementation: Email-Based Authorization

Three authorization mechanisms have been implemented (all optional, global across all providers):

### 1. Exact User Allowlist (allowed_users)
```yaml
# Global configuration (applies to all JWT providers)
allowed_users:
  - "alice@example.com"
  - "bob@company.com"
  - "service.account"
```
- ✅ Implemented in `config.py` and `api.py`
- Simple list of allowed user identifiers (emails, usernames, etc.)
- Case-insensitive exact string matching
- Good for small teams or specific service accounts

### 2. Domain Allowlist (allowed_domains)
```yaml
# Global configuration
allowed_domains:
  - "example.com"
  - "subsidiary.com"
```
- ✅ Implemented in `config.py` and `api.py`
- List of allowed email domains
- Extracts domain from email-like claims (email, preferred_username, upn)
- Case-insensitive matching
- Good for "anyone from our domain" policies

### 3. Regex Pattern Matching (allowed_user_regex)
```yaml
# Global configuration
allowed_user_regex:
  - '^netops-.*@example\.com$'
  - '^[a-z]+\.admin@example\.com$'
```
- ✅ Implemented in `config.py` and `api.py`
- List of regex patterns
- Tested against canonical user identifier and email claim
- Case-insensitive matching (re.IGNORECASE)
- Most flexible for complex policies

## Implementation Details

### Config Schema (`config.py`)
```python
class Settings(SharedSettings):
    # ... existing fields ...
    
    # Simple access control for JWT-authenticated users (OAuth)
    # Precedence: allowed_users > allowed_domains > allowed_user_regex
    # Any match grants access; if all lists are empty, allow all authenticated users.
    allowed_users: list[str] = []
    allowed_domains: list[str] = []
    allowed_user_regex: list[str] = []
```
✅ Implemented in `services/controller/src/tom_controller/config.py` lines 133-135

### Validation Logic (`api.py`)
Authorization check in `_jwt_auth()` function:
1. Check `allowed_users` if configured (exact match, case-insensitive)
2. Check `allowed_domains` if configured (domain extraction from email-like claims)
3. Check `allowed_user_regex` if configured (regex match against canonical user and email)
4. Raise `TomAuthException` on authorization failure

✅ Implemented in `services/controller/src/tom_controller/api/api.py` lines 96-136

### Error Handling
- Authorization failures raise `TomAuthException("Access denied: user not permitted by policy")`
- Returns **401 Unauthorized** (since TomAuthException is caught by FastAPI)
- Note: Could be enhanced to return 403 Forbidden for authorization vs authentication failures

### Combining Rules
When multiple rules are configured:
- **OR** logic between rule types (any match grants access)
- Precedence: allowed_users → allowed_domains → allowed_user_regex
- First match wins, no further checks needed

### Default Behavior
- **No rules configured**: Allow all valid JWTs (backward compatible)
- Maintains backward compatibility
- Explicit opt-in to authorization

### Configuration
- YAML: Set in `tom_config.yaml` at root level
- Environment variables: Lists would be complex, so YAML-only is recommended

## Design Decisions (Implemented)

### 1. Global vs Per-Provider
✅ **Decision**: Global authorization rules that apply to all providers
- Simpler configuration
- Most common use case (same rules for all providers)
- Can be enhanced later with per-provider overrides if needed

### 2. Multiple Patterns
✅ **Decision**: Multiple regex patterns supported
- `allowed_user_regex` is a list of patterns
- OR logic between patterns (any match grants access)

### 3. Case Sensitivity
✅ **Decision**: Case-insensitive matching
- All email and user comparisons use `.lower()`
- Follows RFC 5321 for email addresses
- More intuitive for users

### 4. Precedence and Logic
✅ **Decision**: OR logic with precedence
- Precedence: allowed_users → allowed_domains → allowed_user_regex
- First match grants access
- If all lists empty, allow all authenticated users (backward compatible)

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

✅ Implemented features:
- [x] Email exact match (case insensitive) via `allowed_users`
- [x] Domain matching via `allowed_domains`
- [x] Regex pattern matching via `allowed_user_regex`
- [x] Regex error handling (caught and logged)
- [x] Missing email claim (falls back to preferred_username, upn, sub)
- [x] Combining multiple authorization rules (OR logic)
- [x] No authorization rules (allow all authenticated users)
- [x] Clear error message: "Access denied: user not permitted by policy"

⏳ Future enhancements:
- [ ] Return 403 (not 401) for authorization failures
- [ ] Add unit tests for authorization logic
- [ ] Test with all three providers (Duo, Google, Entra)
- [ ] Per-provider authorization overrides

## Status
✅ **COMPLETED** - Email-based authorization is fully implemented and documented.

## Related Files (Implemented)
- ✅ `services/controller/src/tom_controller/config.py` - Authorization fields added (lines 133-135)
- ✅ `services/controller/src/tom_controller/api/api.py` - Authorization logic implemented (lines 96-136)
- ✅ `tom_config.jwt.example.yaml` - Authorization examples included (lines 23-28)

## Future Enhancements
- Per-provider authorization overrides
- Arbitrary claim matching (e.g., Google `hd`, Entra `groups`)
- Return 403 (not 401) for authorization failures
- Comprehensive unit tests for authorization logic
