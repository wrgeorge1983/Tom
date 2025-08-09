# Security Plan

This document describes the initial security posture for Tom Smykowski.  
It is intentionally simple for early deployment, with clear upgrade paths.

---

## Scope & Phases

- **Phase 1 (MVP)**
  - Controller holds creds (env/file).
  - Worker fetches creds from Controller via `/checkout` over TLS.
  - Auth: single shared HMAC key for request signing.
    - including anti-replay measures.  Timestamp, nonce

- **Phase 2 (future)**
  - Introduce a Creds Service (fronting Vault or similar).
  - Swap shared key to per-worker keys or short-lived job tokens.
  - more sophisticated authentication for workers pehaps.

---

## Threat Model

**Assets**
- Device credentials, rendered configs, parsed outputs, audit logs.

**Trust Boundaries**
- Controller API (HTTPS)
- Queue (Redis Streams)
- Worker containers

**Assumptions**
- TLS is enforced for Controller.
- Redis is not world-reachable; ACLs applied.
- Hosts/containers are patched and monitored.

---

## Guarantees (Phase 1)

- Secrets never enter the queue.
- `/checkout` requests are authenticated (HMAC) and fresh (timestamp + nonce).
- Transport is encrypted (TLS).
- Secrets are redacted from logs and only held in memory on the Controller.

**Residual Risks**
- Single shared HMAC key: if leaked, attacker can call `/checkout` until rotated.
- Compromised worker can use `/checkout` while active.

---

## Controls

### 1. HMAC Request Signing
- Shared `TS_HMAC_SECRET` in both Controller and Workers.
- Each request includes timestamp, nonce, and HMAC signature.
- Controller verifies:
  - HMAC (constant-time compare)
  - Timestamp within ±60s
  - Nonce not reused (cache for 5 min)
- Rate-limit `/checkout`.

### 2. TLS for Controller
- Public endpoint: Let’s Encrypt via Caddy/Traefik/nginx.
- Private endpoint: Internal ACME CA (e.g., smallstep).
- As fallback: Self-signed cert with pinning in Workers.

### 3. Redis Hygiene
- Bind to private network; enable TLS if available.
- Separate ACLs: Controller can write; Workers can read/ack only.

### 4. Logging & Audit
- Log: job ID, worker ID, target, action, cred ref (not secret), result.
- No secret material in logs.
- Log HMAC verification results and replay rejections.

---

We will provide scripts for:
- Generating a new shared HMAC secret.
- Generating TLS keys and certs.
