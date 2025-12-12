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

### v0.7.0
- Redis-backed caching
  - Cache device command outputs at worker level
  - Partial cache support (mix of cached/fresh data)
  - Cache management API endpoints
  - Cache metadata in responses (age, status)
  - Per-request cache control parameters
  - CommandExecutionResult model for structured responses

### v0.8.0
- Better error handling and reporting
- Vault approle support in worker deployment

### v0.10.0
- Multi-command execution with per-command parsing
- Flexible inventory filtering and retry handler
- /inventory/fields API endpoint

### v0.11.0
- Monitoring and metrics system
  - Worker and controller metrics
  - Example Prometheus and Grafana setup in docker-compose.yml

### v0.12.0
- Plugin system for inventory sources
  - Plugin API and architecture
  - Plugin discovery and registration
  - Plugin configuration management
  - Inventory Plugins
    - YAML file
    - SolarWinds NPM API
  - Inventory filtering improvements with inline filters
  - CRUD-managed filter library (API + persistence)
- Dynamic semaphore acquisition retry handling with time-based budgets
  - Extend API and job models with retry and max_queue_wait parameters

### v0.13.0
- Nautobot inventory plugin

### v0.14.0
- NetBox inventory plugin

### v0.15.0 - v0.17.0
- Documentation site with versioning (GitHub Pages + mike)
- Quickstart and sensible-configs example setups
- Update credential management CLI tool (`credload.py`)
- Internal refactoring and code organization

### v0.18.0
- Plugin system for credential stores
  - Vault credential plugin (default, recommended)
  - YAML credential plugin (development only)
  - Plugin discovery, dependency checking, and validation
  - Prefixed plugin settings (`plugin_<name>_*`)

## Future Work

### Reliability
- Worker health monitoring
- Expose Controller and Worker metrics (for e.g. Prometheus)

### Inventory
- Configuration-driven field mapping for custom schemas

### Parsing & Templating
- Jinja2 templating for command generation
- Genie parser integration (maybe)

### Plugin Support
- Credential plugin: AWS Secrets Manager
- Credential plugin: Nautobot Secrets
- Plugin system for device adapters
- Config validation tool (`tom validate-config`) to detect typos and unused keys across main and plugin settings

### User-Context Credentials
- Pass OAuth/JWT identity through to workers
- Worker credential lookup based on authenticated user identity
  - Per-user credentials in Vault (e.g., `secret/tom/users/{email}/credentials`)
  - User+device or user+endpoint credential combinations
- Enables scenarios where different users have different access levels to the same devices
- Supports delegated authentication to backend systems (gRPC endpoints, DHCP servers, etc.)

### UI
- python client library
- golang client library


## Low Priority
### Reliability
- Circuit breakers for unhealthy devices
- Enhanced retry policies

### Security
- Enhanced RBAC from JWT claims (arbitrary claim matching)
- OAuth2 scope-based permissions
- Token refresh flow
