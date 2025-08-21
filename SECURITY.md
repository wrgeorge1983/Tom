# Security Architecture

This document describes the current and planned security architecture for Tom Smykowski.

---

## Current Implementation

**Authentication:**
- API key authentication for tom-core endpoints
- Configurable headers (default: `X-API-Key`)
- User mapping via `key:user` format in configuration

**Credential Management:**
- YAML-based credential store (shared between tom-core and tom-worker)
- Credentials referenced by ID, not embedded in jobs
- Workers read credentials directly from YAML files

**Transport Security:**
- HTTPS/TLS for tom-core API endpoints
- Redis communication (currently plain-text, local network assumed)

## Planned Security Phases

**Phase 1 (Current)**: Direct credential access
- Both API service and workers read from shared YAML credential store
- Simple but functional for development/testing environments

**Phase 2 (Near-term)**: Worker authentication & credential checkout
- Workers authenticate to API service using HMAC signatures
- API service provides credential checkout endpoint (`/checkout`)
- Credentials stay centralized, not distributed to worker filesystems

**Phase 3 (Future)**: Advanced security
- Per-worker HMAC keys (PSK-based join process)
- Short-lived credential tokens
- Integration with external secret stores (Vault, etc.)

---

## Current Security Posture

**Assets Protected:**
- Network device credentials (SSH/SNMP/API keys)
- Device command outputs and configuration data
- Job metadata and audit logs

**Current Controls:**
- API key authentication prevents unauthorized API access
- Credential ID references (not plaintext) in job payloads
- Proper HTTP error codes prevent information leakage
- Structured logging without credential exposure

**Current Gaps:**
- No worker authentication (workers trust shared credential files)
- Redis communication in plaintext
- No credential rotation or expiry
- Limited audit logging

---

## Phase 2 Implementation Plan

**Worker Authentication:**
```python
# Worker registers with API service
POST /worker/register
{
  "worker_id": "unique-worker-id",
  "hmac_signature": "...",
  "timestamp": "...",
  "nonce": "..."
}

# Worker requests credentials for job
POST /credentials/checkout  
{
  "job_id": "...",
  "credential_id": "default",
  "hmac_signature": "...",
  "timestamp": "...",
  "nonce": "..."
}
```

**Security Improvements:**
- Workers must authenticate before accessing credentials
- Credentials never leave the API service filesystem
- HMAC signatures prevent credential theft via compromised Redis
- Audit trail for all credential access

**Migration Path:**
- Add worker authentication alongside existing direct file access
- Gradual migration allows testing without disruption
- Fallback to current approach if authentication fails

---

## Configuration

**Current Environment Variables:**
```bash
# API Authentication
TOM_CORE_AUTH_MODE=api_key
TOM_CORE_API_KEYS=["key1:user1", "key2:user2"]

# Credential Store  
TOM_CORE_CREDENTIAL_FILE=creds.yml
```

**Future Phase 2 Variables:**
```bash
# Worker Authentication
TOM_CORE_WORKER_HMAC_SECRET=shared-secret-key
TOM_CORE_WORKER_AUTH_REQUIRED=true

# Credential Checkout
TOM_CORE_CREDENTIAL_CHECKOUT_ENABLED=true
```
