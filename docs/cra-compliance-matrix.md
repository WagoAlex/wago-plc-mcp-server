# CRA Compliance Matrix — wago-plc-mcp-server

_Maps each CRA Annex I essential requirement to the implementation evidence._
_Version: 2.0.0 | Date: 2026-06-12_

---

## Annex I — Part I: Security requirements

| # | CRA Requirement (Annex I) | Status | Implementation | Evidence |
|---|--------------------------|--------|---------------|---------|
| 1 | No known exploitable vulnerabilities at launch | ⚠️ Partial | grype scans SBOM on every push and weekly | HIGH/CRITICAL findings block CI (`cve-scan.yml`); SARIF in Security tab |
| 2 | Secure by default | ✅ Done | Bearer auth required by default; auto-generated key if none supplied | `src/main.py` `_AuthMiddleware`, `_resolve_api_key()` |
| 2 | Weak credential detection | ✅ Done | Startup WARNING for known-default PLC passwords | `src/main.py` `_parse_plcs_from_env()` |
| 2 | Minimum credential entropy | ✅ Done | `SystemExit(1)` if API key `len < 32` chars | `src/main.py` `_check_key_entropy()` |
| 3 | Access control (authentication) | ✅ Done | Bearer token mandatory on all non-health endpoints | `src/main.py` `_AuthMiddleware` |
| 3 | Access control (authorisation) | ⚠️ Partial | All tools accessible to bearer holder; RBAC deliberately dropped for single-operator model | See threat model §5 |
| 4 | Confidentiality of data in transit | ✅ Done | WDA TLS via `WAGO_TLS_CA` (T2.1); MCP TLS via `MCP_TLS_CERT` (T2.2) | `src/wda_client.py`, `src/main.py` |
| 4 | Confidentiality of credentials at rest | ✅ Done | Docker Secrets at `/run/secrets/`; never printed to logs | `docker-compose.yml`, `src/main.py` |
| 4 | WDA session token security | ✅ Done | Bearer token acquired per-session; reactive 401 re-auth; asyncio.Lock | `src/wda_client.py` `_acquire_token()` |
| 5 | Integrity of data | ✅ Done | Hash-chained audit log with SHA-256 `prev` field; restart-safe seed | `src/main.py` `_audit_log()`, `_seed_audit_hash()` |
| 5 | Integrity verification | ✅ Done | `audit_verify.py` — exit 0 = intact, exit 1 = tampered | `src/audit_verify.py` |
| 6 | Availability | ✅ Done | Rate limiting 60 req/60 s per IP; 429 + Retry-After | `src/main.py` `_AuthMiddleware` |
| 6 | Availability — log disk exhaustion | ✅ Done | Debug log max 30 MB; audit log max 50 MB (20 MB with SIEM) | `src/logging_config.py` |
| 7 | Minimise attack surface | ✅ Done | 13 scoped MCP tools; no shell; no admin API; single container | Architecture by design |
| 7 | Vulnerability monitoring | ✅ Done | Weekly CVE scan; Dependabot for dep updates | `.github/workflows/cve-scan.yml`, `.github/dependabot.yml` |
| 8 | Security update capability | ✅ Done | Docker image distributed via Docker Hub; versioned tags | `build.sh --release` |
| 8 | Update notification | ✅ Done | Version exposed at `/health`; changelog in GitHub releases | `src/main.py` `_HEALTH` |

---

## Annex I — Part II: Vulnerability handling requirements

| # | CRA Requirement | Status | Implementation | Evidence |
|---|----------------|--------|---------------|---------|
| 1 | Identify and document vulnerabilities | ✅ Done | CycloneDX SBOM per release; CVE scan on push | `sbom/`, `build.sh`, `cve-scan.yml` |
| 2 | Address vulnerabilities without delay | ✅ Done | Patch SLA: Critical 7d / High 30d / Medium 90d | `SECURITY.md` |
| 3 | Provide security updates for support period | ✅ Done | 24-month patch support per major version | `SECURITY.md` supported versions table |
| 3 | Coordinated disclosure policy | ✅ Done | Private advisory via GitHub; 3-day acknowledgement SLA | `SECURITY.md` |
| 4 | Share vulnerability information | ✅ Done | GitHub Security Advisories; SARIF to Security tab | Repository settings |
| 5 | ENISA incident reporting process | ✅ Done | 24 h initial notification; BSI / CERT.at contacts documented | `SECURITY.md` |

---

## Annex II — SBOM

| Requirement | Status | Evidence |
|-------------|--------|---------|
| SBOM in machine-readable format | ✅ Done | CycloneDX JSON via syft | `sbom/` directory, CI artifact |
| SBOM covers all direct and transitive deps | ✅ Done | syft scans `uv.lock` + source tree | `cve-scan.yml` artifacts |
| SBOM available on request | ✅ Done | Archived under `sbom/` in repo; CI artifact retention 90 days | — |

---

## Status Legend

| Symbol | Meaning |
|--------|---------|
| ✅ Done | Implemented and verifiable in code |
| ⚠️ Partial | Implemented with a documented limitation or accepted trade-off |
| ❌ Not started | Not yet implemented |

---

## Gaps and Remediation Plan

| Gap | Reason | Plan |
|-----|--------|------|
| Full RBAC (Annex I §3) | Deliberately dropped — single-operator model | Revisit if multi-tenant deployment is required |
| Third-party CVSS ≥ 9 guarantee at launch (Annex I §1) | Transitive deps may have unresolved CVEs in upstream | grype blocks HIGH/CRITICAL in CI; accept remaining after documented review |
