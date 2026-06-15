# EU Declaration of Conformity

_CRA Article 28 — required before placing the product on the EU market._

---

## Product Identification

| Field | Value |
|-------|-------|
| **Product name** | wago-plc-mcp-server |
| **Product description** | MCP server bridging WAGO PLCs to LLM agents via WDA/WDx REST API |
| **Version range** | 2.x (all patch releases) |
| **Docker image** | `wagoalex/wago-plc-mcp-server` |
| **Source repository** | https://github.com/AlexanderFugmann/wago-plc-mcp-server |
| **Product category** | Software — network-connected product with digital elements (CRA Article 3(1)) |

---

## Manufacturer

| Field | Value |
|-------|-------|
| **Name** | Alexander Fugmann |
| **Email** | alexevgenichernich@gmail.com |
| **Country** | EU |

---

## Declaration

The manufacturer hereby declares that the product identified above, in the version
range stated, conforms to the essential cybersecurity requirements set out in
**Annex I of Regulation (EU) 2024/2847** (Cyber Resilience Act).

The following standards and specifications were applied in demonstrating conformity:

| Standard | Scope |
|----------|-------|
| ETSI EN 303 645 v2.1.1 | Baseline cybersecurity for consumer IoT (applied as interim reference pending EN 18031 series publication) |
| OWASP API Security Top 10 2023 | API security controls |
| NIST SP 800-193 | Platform firmware resiliency (audit log integrity) |

---

## Essential Requirements Addressed (Annex I)

### Part I — Security requirements for products with digital elements

| Requirement | Status | Evidence |
|-------------|--------|---------|
| 1. No known exploitable vulnerabilities at launch | Partial | Weekly grype CVE scan on SBOM (T3.1); HIGH/CRITICAL blocks release |
| 2. Secure by default configuration | ✅ | Bearer auth mandatory (T1); weak password warning (T5.1); entropy enforcement (T5.2) |
| 3. Protection of confidentiality | ✅ | Docker Secrets for credentials; TLS available on both legs (T2.1, T2.2) |
| 4. Protection of integrity | ✅ | Hash-chained audit log (T4.1); tamper detection via `audit_verify.py` |
| 5. Availability protection | ✅ | Rate limiting 60 req/60 s per IP (T2.3); log rotation prevents disk exhaustion |
| 6. Minimised attack surface | ✅ | Single-container deployment; 13 scoped tools; no shell exposure |
| 7. Vulnerability disclosure | ✅ | SECURITY.md with CVD policy and patch SLA |
| 8. Security updates | ✅ | Patch SLA defined (Critical 7d / High 30d / Medium 90d); automated dep updates (T3.2) |

### Part II — Vulnerability handling requirements

| Requirement | Status | Evidence |
|-------------|--------|---------|
| 1. Identify and document vulnerabilities | ✅ | SBOM (CycloneDX, generated per release); CVE scan (T3.1) |
| 2. Address vulnerabilities without delay | ✅ | Patch SLA in SECURITY.md (T3.4) |
| 3. Apply effective and regular security tests | ✅ | grype scan on every push + weekly schedule |
| 4. Share information about vulnerabilities | ✅ | GitHub Security Advisories; SECURITY.md coordinated disclosure |

---

## Technical File Location

The technical file (CRA Article 31) is held by the manufacturer and available to
market surveillance authorities on request. It includes:

- This declaration
- Architecture documentation (`docs/threat-model.md`)
- CRA compliance matrix (`docs/cra-compliance-matrix.md`)
- SBOM archives (`sbom/`)
- CVE scan results (GitHub Security tab, CI artifacts)
- Test evidence (GitHub Actions logs)

---

## Authorised Signatory

| Field | Value |
|-------|-------|
| **Name** | Alexander Fugmann |
| **Role** | Manufacturer / Lead Engineer |
| **Date** | 2026-06-12 |
| **Place** | EU |

_By maintaining this document in the repository, the manufacturer confirms that
the product as shipped conforms to the requirements stated above. This document
must be updated when the conformity assessment changes materially._

---

_This is a self-declaration under CRA Article 28(1). The product does not fall
into the critical product categories of Annex III or IV requiring third-party
conformity assessment._
