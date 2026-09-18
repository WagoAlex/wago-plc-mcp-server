# Security

# Security

## API key management

The server gets the MCP API key from the first source that exists:

1. **Docker Secret** `/run/secrets/mcp_api_key`. Recommended for production.
2. **Environment variable** `MCP_API_KEY`.
3. **Persisted file** `./data/mcp_api_key`. The server makes this file at the first start. The file stays after you recreate the container.
4. **New key.** The server makes a new key if no other source exists.

To read the key from a Docker Secret, read the file on the host. You do not need the container for this:

```bash
cat secrets/mcp_api_key.txt
```

To read an auto-generated key (source 3 or 4), use the container volume:

```bash
docker exec wmcp cat /app/data/mcp_api_key
```

Use the Docker Secret after initial tests. You control the key file, and the key stays out of container exec history.

To make a new auto-generated key:

```bash
# Regenerate (only affects the auto-generated/persisted key - has no effect
# if a Docker Secret or MCP_API_KEY env var is set, since those outrank it)
docker exec wmcp python src/mcp_keygen.py
docker restart wmcp
```

## TLS configuration

TLS is off by default on both connections. At startup, the server logs a warning for each connection without TLS.

**Server to PLC (WDA).** Select one option:

```bash
# Option A: Per-PLC cert pinning (recommended for self-signed certs)
openssl s_client -connect 192.168.1.10:443 </dev/null 2>/dev/null \
  | openssl x509 > secrets/plc_cert_192_168_1_10
# Declare the secret in docker-compose.yml and restart

# Option B: Private CA bundle
WAGO_TLS_CA=/run/secrets/wago_ca.pem

# Option C: System trust store (only if PLC certs are CA-signed)
WAGO_TLS_CA=true
```

**Client to server (MCP endpoint):**

```bash
openssl req -x509 -newkey rsa:4096 \
  -keyout secrets/mcp_tls_key.pem \
  -out secrets/mcp_tls_cert.pem \
  -days 365 -nodes -subj "/CN=wago-mcp"
```

```env
MCP_TLS_CERT=/run/secrets/mcp_tls_cert
MCP_TLS_KEY=/run/secrets/mcp_tls_key
```

**Require TLS on both connections:**

```env
SECURITY_PROFILE=hardened
```

With this setting, the server stops at startup (`SystemExit(1)`) before it connects to a PLC, if one of these conditions is true:

- `WAGO_TLS_CA` is not set, or is `false` or `0`.
- `MCP_TLS_CERT` or `MCP_TLS_KEY` is not set.

The check makes sure that TLS is configured. It does not check if a trusted CA signed the certificate. A self-signed certificate passes.

## Audit log

The server adds each `set_parameters` and `invoke_method` call to a hash-chained JSON Lines log.
Each entry contains the hash of the previous entry, so you can find changes to the file.

```
Entry 1  {"ts":"…","action":"set_parameters",…,"prev":"0000…0000"}  ← genesis
Entry 2  {"ts":"…","action":"invoke_method",…,"prev":"a3f1…c2d8"}
Entry 3  {"ts":"…","action":"set_parameters",…,"prev":"7b2e…91fa"}
```

Each entry has the timestamp, PLC IP, parameter IDs and values, and `key-<first 8 characters of the API key>`.
With one key for each engineer, you can see who made each change.

```bash
# Tail live log
docker exec wmcp tail -f /app/data/audit.log

# Verify chain integrity
docker exec wmcp python src/audit_verify.py --log /app/data/audit.log
# → [PASS] Chain intact - 42 entries verified (/app/data/audit.log)
```

To send each record to a syslog collector outside the host, set `AUDIT_SYSLOG=udp://<collector>:514` or `tcp://<collector>:514`.

## Security features

| Feature | Status |
|---------|--------|
| Bearer auth on `/mcp` | ✅ Auto-generated key, Docker Secret or environment override. `/health` is exempt. |
| Rate limiting | ✅ 60 requests in 60 s for each source IP. Returns `429` with `Retry-After`. |
| Auth failure alerts | ✅ WARNING for each failure. ERROR after 10 failures in sequence from one IP. |
| WDA Bearer token auth | ✅ The server sends credentials one time and refreshes the cached token on 401. |
| Hash-chained audit log | ✅ JSON Lines on the `./data` volume |
| Default password warning | ✅ WARNING at startup if a PLC uses the factory default password |
| TLS - WDA connections | ⚙️ Off by default. Enable with `WAGO_TLS_CA` or a per-PLC Docker Secret. |
| TLS - MCP endpoint | ⚙️ Off by default. Enable with `MCP_TLS_CERT` and `MCP_TLS_KEY`. |
| CycloneDX SBOM | ✅ Published with each release image |
| Docker Secrets | ✅ For PLC passwords, the MCP key, and TLS certificates |
| CVE scanning | ✅ Weekly grype scan of the SBOM. HIGH or CRITICAL findings fail CI. |

## Security and CRA compliance

This project targets compliance with the EU Cyber Resilience Act (Regulation 2024/2847).

| Document | Content |
|----------|---------|
| [SECURITY.md](../SECURITY.md) | Vulnerability reports, patch SLA, support lifetime |
| [docs/threat-model.md](threat-model.md) | STRIDE risk assessment |
| [docs/cra-compliance-matrix.md](cra-compliance-matrix.md) | Annex I requirements mapped to evidence |
| [docs/eu-declaration-of-conformity.md](eu-declaration-of-conformity.md) | CRA Article 28 self-declaration |
| [docs/technical-file.md](technical-file.md) | CRA Article 31 technical file index |

To report a vulnerability, follow [SECURITY.md](../SECURITY.md). Do not open a public issue.
