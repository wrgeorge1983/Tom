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
  - Base JWT validator with JWKS support
  - Duo Security validator (✅ tested and working)
  - Provider-specific validators for Google, GitHub, Microsoft Entra ID (⚠️ speculative/untested)
  - Hybrid authentication mode (JWT + API keys)
  - YAML-based provider configuration
  - Bearer token validation in API
  - PKCE-based CLI authentication (Python reference implementation)

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
- TextFSM, TTP, maybe genie integration for output parsing
- Jinja2 templating for command generation

### Security
- ~~JWT/OAuth2 authentication support~~ ✅ v0.6.0
- Role-based access control (RBAC) from JWT claims
- OAuth2 scope-based permissions
- Token refresh flow
- Frontend OAuth flow handler (for testing/demo)

### Plugin model
- Plugin API
- Migrate inventory and credential stores to plugins

### UI
- Web UI
- CLI
- python client library
- golang client library
