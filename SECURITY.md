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

- **Phase 1.5 (enhanced auth)**
  - Implement "PSK for join → per-worker HMAC key" pattern.
  - Workers use shared PSK to establish unique HMAC keys during join.
  - Optional: Wrap join step in X25519 key exchange for defense-in-depth.

- **Phase 2 (future)**
  - Introduce a Creds Service (fronting Vault or similar).
  - Swap to short-lived job tokens or certificate-based auth.
  - Full per-worker key rotation and revocation.

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
- Phase 1: Single shared HMAC key - if leaked, attacker can call `/checkout` until rotated.
- Phase 1.5: Compromised PSK allows generating new worker keys, but limits blast radius.
- Any compromised worker can use `/checkout` while its key remains valid.

---

## Controls

### 1. HMAC Request Signing

**Phase 1 (current):**
- Shared `TS_HMAC_SECRET` in both Controller and Workers.
- Each request includes timestamp, nonce, and HMAC signature.
- Controller verifies signature, timestamp (±60s), and nonce uniqueness.

**Phase 1.5 (per-worker keys):**
- Shared PSK for worker join process to establish unique HMAC keys.
- Each worker gets individual HMAC key via authenticated join handshake.
- Optional X25519 wrapping ensures PSK-derived keys never transmitted in clear.
- Controller maintains mapping of worker IDs to their unique HMAC keys.

All phases include:
- Constant-time HMAC comparison
- Nonce cache (5 min) for replay protection
- Rate-limiting on `/checkout` and join endpoints

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
