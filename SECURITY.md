# Security Architecture

## The Demo Implementation in this Repo (docker compose)

- **API Security**: API key-based client authentication with configurable headers.
    OAuth/JWT authentication is available but requires external identity provider setup.
    TLS is not provided (add via reverse proxy).

- **Credential Security**: Credentials for device access stored in HashiCorp Vault and
    fetched by workers directly. Credentials are never written to disk, all communication is 
    encrypted. Credentials are referenced by ID in jobs unless the user explicitly 
    opts to include raw credentials in the job payload. HashiCorp Vault is in "dev mode"
    which is known to be insecure and unsuitable for production. Use `credload.py` to load
    demo credentials into Vault.

- **Redis**: Connections are TLS encrypted with self-signed certificates. Clients do 
    not have certificates and do not validate the server certificate. Clients 
    do not authenticate using redis AUTH.


## Making it ready for production

- **API Authentication**: For demos, use API keys. For production, configure JWT/OAuth 
    with your identity provider (Duo, Google, Entra ID, etc.). See `docs/oauth-implementation.md`.
    Add authorization rules (`allowed_users`, `allowed_domains`, `allowed_user_regex`) as needed.

- **TLS for the API**: Should be added by a reverse proxy.

- **Credential Security**: HashiCorp Vault or other suitable credential store
    should be configured for production according to their documentation and 
    best practices.

- **Redis**: TLS certificates should not be self-signed. Also, client authentication 
    should be added. Passwords as a minimum, but better would be to issue and use valid client certificates.
    Consider using managed Redis services (AWS ElastiCache, Redis Cloud, etc.).
