# Security Architecture

## The Demo Implementation in this Repo (docker compose)

- **API Security**: API key-based client authentication with configurable headers.
    TLS is not available.

- **Credential Security**: Creds for device access stored in Hashicorp Vault and
    fetched by workers directly.  Creds are never written to disk, all communication is 
    encrypted.  Creds are references by Id in the jobs themselves unless the user explicitly 
    opts to include raw creds in the job payload.  Hashicorp Vault is in "dev mode"
    which is known to be insecure and unsuitable for production.

- **Redis**: Connections are TLS encrypted with self-signed certs.  Clients do 
    not have certificates and do not validate the server certificate.  Clients 
    do not authenticate using redis AUTH.


## Making it ready for production

- **TLS for the API**: should be added by a reverse proxy.

- **Credential Security**: Hashicorp Vault or other suitable credential store
    should be configured for production according to their documentation and 
    best practices.

- **Redis**: TLS certificates should not be self-signed. Also, client authentication 
    should be added.  Passwords as a minimum, but better would be to issue and use valid client certificates.
