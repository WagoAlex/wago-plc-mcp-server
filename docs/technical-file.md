# Technical File — wago-plc-mcp-server

_CRA Article 31 — must be held by the manufacturer and made available to market_
_surveillance authorities on request for 10 years after the product is placed on the market._

_Version: 2.0.0 | Date: 2026-06-12_

---

## Index of Technical File Elements

This document is the index. The full technical file consists of this index plus
the referenced artefacts — all held in this repository or as CI artefacts.

| Element (Art. 31) | Location | Format |
|-------------------|----------|--------|
| Product description and intended use | `README.md` | Markdown |
| Design and architecture | `docs/threat-model.md` §1–2 | Markdown |
| Security risk assessment | `docs/threat-model.md` §3–4 | Markdown, STRIDE |
| List of cybersecurity standards applied | `docs/eu-declaration-of-conformity.md` | Markdown |
| CRA Annex I compliance evidence | `docs/cra-compliance-matrix.md` | Markdown |
| SBOM | `sbom/sbom-<version>.json` | CycloneDX JSON |
| Vulnerability handling policy | `SECURITY.md` | Markdown |
| Patch SLA | `SECURITY.md` — Patch SLA table | Markdown |
| Support lifetime | `SECURITY.md` — Supported Versions | Markdown |
| CVE scan results | GitHub Actions → Security tab; CI artifact `grype-report-*` | SARIF |
| Test evidence | GitHub Actions logs; `docker exec wmcp python src/audit_verify.py` | Log output |
| EU Declaration of Conformity | `docs/eu-declaration-of-conformity.md` | Markdown |

---

## Product Description

**wago-plc-mcp-server** is an open-source MCP (Model Context Protocol) server
that bridges LLM agents to a fleet of WAGO PLCs via the WDA/WDx REST API.
It is deployed as a Docker container (`wagoalex/wago-plc-mcp-server`) on a host
with network access to the PLC subnet.

**Intended use:**
- Industrial automation environments where LLM agents need read/write access to PLC parameters
- Operator-supervised deployments; not designed for unattended autonomous control
- Single-operator, private-network deployments (not SaaS or multi-tenant)

**Out of intended use:**
- Safety-critical control loops where a software failure could cause physical harm
- Deployments without network segmentation between the agent endpoint and the PLC subnet

---

## Architecture Summary

```
[LLM Agent]  --HTTPS/Bearer-->  [MCP Server :6042]  --HTTPS/WDA Bearer-->  [WAGO PLCs]
                                        │
                               [Audit Log / SIEM]
```

Components:
- `src/main.py` — FastMCP server, ASGI middleware, tool definitions
- `src/wda_client.py` — async HTTP client for WDA REST API
- `src/plc_manager.py` — PLC registry, parallel init, TLS cert selection
- `src/logging_config.py` — loguru setup, syslog sink
- `src/audit_verify.py` — standalone hash-chain verifier

---

## Security Controls Summary

See `docs/cra-compliance-matrix.md` for the full mapping.

Key controls implemented:
- Bearer authentication with entropy enforcement
- Rate limiting (60 req/60 s per IP)
- Hash-chained tamper-evident audit log
- WDA TLS verification (configurable CA or per-PLC cert pinning)
- MCP endpoint TLS (optional, operator-configured)
- Docker Secrets for credential storage
- Weekly CVE scanning via grype
- Automated dependency updates via Dependabot
- SIEM/syslog export of audit events
- Auth failure alerting (10-failure threshold)

---

## Conformity Assessment Route

This product is a **default category** software product under CRA Article 3(1).
It does not fall within the critical categories of Annex III or IV.

Conformity assessment route: **self-declaration** per CRA Article 28(1).

The EU Declaration of Conformity is at `docs/eu-declaration-of-conformity.md`.

---

## Document Retention

This technical file must be retained for **10 years** from the date the product
is first placed on the EU market.

The repository (including git history) constitutes the primary retention mechanism.
For long-term archival, tag-based GitHub releases preserve the technical file
at each version boundary.

---

## Change History

| Version | Date | Changes |
|---------|------|---------|
| 2.0.0 | 2026-06-12 | Initial technical file; full CRA Tier 1–5 implementation |
