# Security Policy

_wago-plc-mcp-server — CRA Article 11, 13(6), 13(7), 14 compliance document._

---

## Supported Versions

Security patches are provided for the current major release series.
Support for a major version ends **24 months after the next major release**,
or at end-of-sale, whichever is later.

| Version | Status         | Security patches until |
|---------|----------------|------------------------|
| 2.x     | ✅ Supported   | At least 2027-06-12    |
| 1.x     | ❌ End of life | —                      |

End-of-support dates are updated here when a new major version is released.

---

## Reporting a Vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

Use GitHub's private advisory mechanism instead:

1. Go to the repository → **Security** → **Advisories** → **New draft security advisory**
2. Describe the vulnerability, affected versions, and reproduction steps
3. We will acknowledge within **3 business days**

Alternatively, email: **alexevgenichernich@gmail.com**  
Subject line: `[SECURITY] wago-plc-mcp-server — <one-line summary>`

PGP encryption is not required but is welcome. If you need the public key,
request it via email and it will be provided within 1 business day.

---

## Patch SLA (CRA Article 13(6))

| CVSS Score     | Severity | Acknowledgement | Fix shipped    |
|----------------|----------|-----------------|----------------|
| ≥ 9.0          | Critical | 24 hours        | 7 days         |
| 7.0 – 8.9      | High     | 3 business days | 30 days        |
| 4.0 – 6.9      | Medium   | 10 business days | 90 days       |
| 0.1 – 3.9      | Low      | Next release    | —              |

Actively exploited vulnerabilities (regardless of CVSS) are treated as Critical.

Fixes are shipped as patched Docker images on Docker Hub
(`wagoalex/wago-plc-mcp-server`) and tagged releases on GitHub.

---

## Coordinated Disclosure

We follow **responsible coordinated disclosure**:

1. Reporter submits vulnerability privately
2. We acknowledge within the SLA above
3. We develop and test a fix
4. We notify the reporter before public release
5. We release the fix and publish a GitHub Security Advisory
6. Reporter may publish their own write-up 7 days after our advisory is public

We credit reporters in the advisory unless anonymity is requested.

---

## ENISA Incident Reporting (CRA Article 14)

For incidents involving actively exploited vulnerabilities or significant impacts
on users in the EU:

- Initial notification to the relevant national CSIRT within **24 hours** of discovery
- Intermediate report within **72 hours**
- Final report within **30 days**

Relevant CSIRTs by country:
- Germany: [BSI](https://www.bsi.bund.de/) — meldestelle@bsi.bund.de
- Austria: [CERT.at](https://www.cert.at/)
- EU coordination: [ENISA](https://www.enisa.europa.eu/)

---

## Scope

This policy covers the **wago-plc-mcp-server** software and its Docker image.
It does not cover the WAGO PLC firmware, WDA REST API, or third-party dependencies
(report those to the respective upstream maintainers).

---

## Out of Scope

- Issues in WAGO firmware or WDA/WDx API — report to WAGO directly
- Network-layer attacks against the PLC subnet — contact your SCADA/OT security team
- Theoretical vulnerabilities without a realistic attack path

---

## Hall of Fame

Researchers who responsibly disclosed vulnerabilities will be credited here
(unless they request anonymity).

_No reports received yet._
