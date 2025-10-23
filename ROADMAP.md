# Tom Smykowski Roadmap

## Completed

### v0.2.0
- Queue-based job processing with SAQ + Redis
- Per-device concurrency control
- YAML inventory and credential stores
- API key authentication

### v0.3.0  
- HashiCorp Vault credential store
- SolarWinds SWIS inventory with filtering
- Multi-command execution with structured results
- YAML config file support

### v0.4.0
- Logo!
- Redis TLS encryption and authentication support

### v0.5.0
- rename core->controller
- docs

### v0.6.0
- JWT authentication support
  - Base JWT validator with JWKS and OIDC discovery
  - Duo Security validator (tested and working)
  - Google OAuth validator (tested and working)
  - Microsoft Entra ID validator (fully supported)
  - Hybrid authentication mode (JWT + API keys)
  - YAML-based provider configuration
  - Bearer token validation in API
  - PKCE-based CLI authentication (Python reference implementation)
- Email-based authorization
  - Exact user allowlist (allowed_users)
  - Domain allowlist (allowed_domains)
  - Regex pattern matching (allowed_user_regex)
  - Proper 403 vs 401 error codes
- Output parsing integration
  - TextFSM parser with 929 built-in ntc-templates
  - TTP parser with inline template support
  - Custom template indexes for auto-discovery
  - Template selection metadata in responses
  - Parsing API endpoints

## Future Work

### Reliability
- Circuit breakers for unhealthy devices
- Enhanced retry policies
- Configurable caching by device and command
- Worker health monitoring
- Expose Controller and Worker metrics (for e.g. Prometheus)

### Inventory
- Additional inventory source adapters (NetBox, Nautobot, etc.)
- Configuration-driven field mapping for custom schemas

### Parsing & Templating
- Jinja2 templating for command generation
- Genie parser integration (maybe)

### Security
- Enhanced RBAC from JWT claims (arbitrary claim matching)
- OAuth2 scope-based permissions
- Token refresh flow
- Frontend OAuth flow handler (for testing/demo)
- Per-provider authorization overrides

### Plugin model
- Plugin API
- Migrate inventory and credential stores to plugins

### UI
- Web UI
- CLI
- python client library
- golang client library
