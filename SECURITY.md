# Security Policy

_wago-plc-mcp-server - CRA Article 11, 13(6), 13(7), 14 compliance document._

---

## Supported Versions

We supply security patches for the current major release series.
Support for a major version stops **24 months after the next major release**,
or at end-of-sale. The later date applies.

| Version | Status         | Security patches until |
|---------|----------------|------------------------|
| 2.x     | ✅ Supported   | At least 2027-06-12    |
| 1.x     | ❌ End of life | -                      |

When we release a new major version, we update the end-of-support dates on this page.

---

## Reporting a Vulnerability

**Do not open a public GitHub issue for a security vulnerability.**

Use the private advisory function of GitHub:

1. In the repository, go to **Security** → **Advisories** → **New draft security advisory**.
2. Describe the vulnerability, the affected versions, and the steps to reproduce it.
3. We send an acknowledgement within **3 business days**.

You can also send an email to **alexander.fugmann@wago.com**.
Use this subject line: `[SECURITY] wago-plc-mcp-server - <one-line summary>`

PGP encryption is optional. If you need the public key, ask for it by email.
We send it within 1 business day.

---

## Patch SLA (CRA Article 13(6))

| CVSS Score     | Severity | Acknowledgement | Fix shipped    |
|----------------|----------|-----------------|----------------|
| ≥ 9.0          | Critical | 24 hours        | 7 days         |
| 7.0 - 8.9      | High     | 3 business days | 30 days        |
| 4.0 - 6.9      | Medium   | 10 business days | 90 days       |
| 0.1 - 3.9      | Low      | Next release    | -              |

We treat a vulnerability that attackers actively exploit as Critical, for all CVSS scores.

We ship fixes as patched Docker images on Docker Hub
(`wagoalex/wago-plc-mcp-server`) and as tagged releases on GitHub.

---

## Coordinated Disclosure

We use **responsible coordinated disclosure**:

1. The reporter sends the vulnerability to us privately.
2. We send an acknowledgement within the SLA above.
3. We make and test a fix.
4. We tell the reporter before the public release.
5. We release the fix and publish a GitHub Security Advisory.
6. The reporter can publish a write-up 7 days after our advisory is public.

We name the reporter in the advisory, unless the reporter asks to stay anonymous.

---

## ENISA Incident Reporting (CRA Article 14)

For an incident with an actively exploited vulnerability, or with a significant effect
on users in the EU:

- Initial notification to the related national CSIRT within **24 hours** of discovery
- Intermediate report within **72 hours**
- Final report within **30 days**

Related CSIRTs by country:
- Germany: [BSI](https://www.bsi.bund.de/) - meldestelle@bsi.bund.de
- Austria: [CERT.at](https://www.cert.at/)
- EU coordination: [ENISA](https://www.enisa.europa.eu/)

---

## Scope

This policy covers the **wago-plc-mcp-server** software and its Docker image.
It does not cover the WAGO PLC firmware, the WDA REST API, or third-party dependencies.
Report problems in those to their upstream maintainers.

---

## Out of Scope

- Problems in WAGO firmware or in the WDA/WDx API. Report them to WAGO.
- Network-layer attacks on the PLC subnet. Contact your SCADA/OT security team.
- Theoretical vulnerabilities without a realistic attack path

---

## Hall of Fame

We name researchers who responsibly reported vulnerabilities here,
unless they ask to stay anonymous.

_No reports received yet._
