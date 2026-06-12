# Threat Model — wago-plc-mcp-server

_CRA Annex I, Part I — security risk assessment. STRIDE per trust boundary._
_Version: 2.0.0 | Date: 2026-06-12 | Author: Engineering_

---

## 1. System Overview

```
[LLM Agent / Claude Desktop]
        │  HTTPS + Bearer token
        ▼
[wago-plc-mcp-server :6042]  ← audit log → /app/audit.log → SIEM
        │  HTTPS + WDA Bearer token
        ▼
[WAGO PLCs — CC100 / PFC200 / PFC300]
        │  WDA REST API /wda
        ▼
[OT Field Devices — I/O, sensors, actuators]
```

**Trust boundaries:**
- B1: Agent ↔ MCP server (public/semi-public network)
- B2: MCP server ↔ PLC (private OT subnet)
- B3: MCP server ↔ host filesystem (container boundary)

---

## 2. Assets

| Asset | Confidentiality | Integrity | Availability |
|-------|----------------|-----------|--------------|
| PLC parameter values (process data) | Medium | High | High |
| PLC credentials (username / password) | High | High | Medium |
| MCP API key | High | High | Medium |
| WDA Bearer tokens (ephemeral) | Medium | High | Low |
| Audit log | Low | High | Medium |
| MCP server binary / config | Medium | High | High |

---

## 3. Threat Actors

| Actor | Motivation | Capability |
|-------|-----------|-----------|
| Compromised MCP client / rogue agent | Unintended PLC writes | Low (API access only) |
| External attacker on MCP endpoint | Data exfil, pivot to OT | Medium |
| OT subnet MITM | Intercept WDA traffic | Low–Medium |
| Insider (operator with API key) | Unauthorized PLC changes | High |
| Supply chain (dep vulnerability) | Remote code execution | Medium |

---

## 4. STRIDE Analysis per Trust Boundary

### B1 — Agent ↔ MCP Server

| Threat | STRIDE | Mitigation | Residual risk |
|--------|--------|-----------|---------------|
| Unauthenticated tool calls | Spoofing | Bearer auth (T1), API key entropy check (T5.2) | Low |
| Brute-force API key | Spoofing | Rate limiting 60 req/60 s (T2.3), auth failure alerts at 10 failures (T4.2) | Low |
| Traffic interception | Info disclosure | MCP TLS via `MCP_TLS_CERT` / `MCP_TLS_KEY` (T2.2) | Medium — TLS optional, operator must enable |
| Replay of captured token | Spoofing | HTTPS in transit; token is long-lived — rotation is operator responsibility | Medium |
| Malicious parameter payload | Tampering | WDA API validates values; server passes through without re-execution | Low |
| Audit log tampering | Tampering | Hash-chained log (T4.1); verification via `audit_verify.py` | Low |
| Log flooding | DoS | Rate limiting (T2.3); log rotation + size caps (T4.3) | Low |

### B2 — MCP Server ↔ PLC

| Threat | STRIDE | Mitigation | Residual risk |
|--------|--------|-----------|---------------|
| WDA credential interception | Info disclosure | WDA Bearer token auth (T3); TLS via `WAGO_TLS_CA` (T2.1) | Medium — TLS optional on WDA side; PLC uses self-signed certs |
| Credential leakage via logs | Info disclosure | Credentials stored in Docker Secrets / env; log filters do not print credentials | Low |
| Default PLC password | Spoofing | Startup warning on known-weak passwords (T5.1) | Medium — operator must act on warning |
| Unauthorized method invocation | Elevation of privilege | All invocations logged to audit (T4) with AUDIT level | Low |
| WDA token replay | Spoofing | Tokens are ephemeral (per-session); reactive 401 re-auth (T3) | Low |

### B3 — Container ↔ Host Filesystem

| Threat | STRIDE | Mitigation | Residual risk |
|--------|--------|-----------|---------------|
| Secret extraction from env | Info disclosure | Docker Secrets at `/run/secrets/` preferred over env vars | Low |
| Audit log deletion | Tampering | SIEM forwarding (T4.3); hash chain detects truncation | Medium — requires SIEM to be enabled |
| Container escape | Elevation | Standard Docker isolation; no `--privileged` flag | Low |

---

## 5. Accepted Trade-offs

| Decision | Rationale |
|----------|-----------|
| TLS optional on WDA side (`verify=False` default) | WAGO PLCs ship with self-signed certs; operators on isolated OT subnets may not have a CA. Verified TLS is available via `WAGO_TLS_CA`. |
| TLS optional on MCP endpoint | Operators behind a TLS-terminating reverse proxy do not need double TLS. Warning is logged if disabled. |
| No RBAC | Single-operator deployment; tool-level access control belongs in the LLM agent policy, not the server. |
| Long-lived MCP token | Short-lived tokens require a token issuance service. Operator rotation via `mcp_keygen.py` is acceptable for self-hosted use. |

---

## 6. Mitigations Summary (implemented)

| Control | Tier | Status |
|---------|------|--------|
| Bearer authentication | T1 | ✅ |
| Rate limiting (60 req/60 s/IP) | T2.3 | ✅ |
| WDA TLS verification | T2.1 | ✅ |
| MCP endpoint TLS | T2.2 | ✅ |
| WDA Bearer token auth | T3 | ✅ |
| Hash-chained audit log | T4.1 | ✅ |
| Auth failure alerts | T4.2 | ✅ |
| SIEM/syslog export | T4.3 | ✅ |
| Weak password warning | T5.1 | ✅ |
| API key entropy enforcement | T5.2 | ✅ |
| SBOM | T5 | ✅ |
| CVE scanning (weekly) | T3.1 | ✅ |

---

## 7. Residual Risks (accepted)

1. **WDA MITM on isolated OT subnet** — if operator does not set `WAGO_TLS_CA`.
   Risk acceptance: OT subnet is assumed air-gapped or VPN-isolated.

2. **Token replay within session** — MCP Bearer token is long-lived.
   Risk acceptance: operator rotates on suspicion; rate limiting bounds abuse.

3. **Insider threat** — operator with API key has full tool access.
   Risk acceptance: single-operator model; audit log provides accountability.

4. **Default PLC password** — server warns but does not block.
   Risk acceptance: PLC access policy is outside server scope.
