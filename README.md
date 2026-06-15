[![Docker Hub](https://img.shields.io/docker/pulls/wagoalex/wago-plc-mcp-server)](https://hub.docker.com/r/wagoalex/wago-plc-mcp-server)
[![License: MPL-2.0](https://img.shields.io/badge/License-MPL%202.0-brightgreen.svg)](LICENSE)

# wago-plc-mcp-server

> MCP server that connects WAGO PLCs to LLM agents via the WDx/WDA REST API.

Ask an AI assistant to read sensor values, change configuration, trigger firmware updates, or monitor entire PLC fleets — with no custom code.

```
 MCP Client (Claude Desktop / Claude Code / OpenClaw)
        │
        │  Bearer token  +  optional TLS ◄── MCP_TLS_CERT + MCP_TLS_KEY
        │
        ▼
 ┌──────────────────────────────────────────────────────┐
 │          wago-plc-mcp-server  (Docker, port 6042)    │
 │                                                      │
 │   Bearer auth · Rate limiting · Audit log (chained)  │
 └────────────────────────┬─────────────────────────────┘
                          │
                          │  WDA Bearer token  +  TLS ◄── WAGO_TLS_CA / per-PLC cert
                          │
              ┌───────────┴───────────┐
              ▼                       ▼
    WAGO PLC 192.168.1.10    WAGO PLC 192.168.1.11
    PFC200 / PFC300 / CC100  Edge Controller
```

---

## Supported Hardware

| Device | Notes |
|--------|-------|
| PFC200 Gen 2 | Full support |
| PFC300 | Full support |
| CC100 | Full support — set `WAGO_TIMEOUT_SECONDS=45` (slow ARM CPU) |
| Edge Controller | Full support — Docker and CODESYS runtime visible via WDA |

Requires firmware **≥ 03.x** with WDx/WDA REST API enabled. Tested up to firmware 04.09.01.

---

## Features

- **13 MCP tools** — discover, read, write, invoke methods, monitor
- **Fleet-wide parallel reads** — query one parameter across all PLCs in a single tool call
- **Server-side watchlists** — efficient repeated polling without repeated handshakes
- **Enum resolution** — raw integer enum values translated to human-readable labels
- **Writeability pre-validation** — read-only parameters rejected before hitting the PLC
- **Fuzzy parameter search** — find parameters by keyword without knowing exact IDs (up to 255 results)
- **Dual transport** — Streamable HTTP (default) or SSE, switched via env var
- **Docker-first** — single container, host networking for routed PLC subnets

### Security

| Feature | Status | Details |
|---------|--------|---------|
| Bearer auth on `/mcp` | ✅ | Auto-generated key; Docker Secret + env override; `/health` exempt |
| Rate limiting | ✅ | 60 req / 60 s per source IP; `429` with `Retry-After` |
| Auth failure alerts | ✅ | WARNING per failure; ERROR alert at 10 consecutive failures from same IP |
| WDA Bearer token auth | ✅ | Credentials sent once; cached token refreshed reactively on 401 |
| Hash-chained audit log | ✅ | Every write is a tamper-evident JSON-lines entry with `prev` SHA-256 |
| Default password warning | ✅ | Startup WARNING if factory default password detected |
| TLS — WDA connections | ⚙️ | Off by default; enable with `WAGO_TLS_CA` or per-PLC Docker Secret |
| TLS — MCP endpoint | ⚙️ | Off by default; enable with `MCP_TLS_CERT` + `MCP_TLS_KEY` |
| CycloneDX SBOM | ✅ | Published alongside every release image |
| Docker Secrets | ✅ | PLC passwords, MCP key, TLS certs all mountable as secrets |
| CVE scanning | ✅ | Weekly grype scan on SBOM; HIGH/CRITICAL fails CI |
| Dependabot | ✅ | Weekly PRs for pip, Docker, and GitHub Actions dep updates |

For the vulnerability disclosure policy, patch SLA, and support lifetime see [SECURITY.md](SECURITY.md).

---

## Quick Start

### 1. Clone and configure

```bash
git clone https://github.com/WagoAlex/wago-plc-mcp-server.git
cd wago-plc-mcp-server
cp _env .env
```

Edit `.env` with your PLC details:

```env
WAGO_PLC_HOSTS=192.168.1.10,192.168.1.11,192.168.1.12
DEFAULT_PLC_USERNAME=admin
DEFAULT_PLC_PASSWORD=wago
PORT=6042
WAGO_TIMEOUT_SECONDS=15     # use 45 for CC100
```

> For fleets with mixed passwords, use per-PLC overrides:
> `PLC_PASSWORDS_192_168_1_11=secret` (IP with underscores).

### 2. Create the PLC password secret

```bash
mkdir -p secrets
echo "your-plc-password" > secrets/plc_default_password.txt
chmod 600 secrets/plc_default_password.txt
```

### 3. Start

```bash
docker compose up -d
docker logs wmcp -f
```

The container uses `network_mode: host` so it can reach PLCs on routed subnets directly. On first boot the server prints the auto-generated API key — **copy it now**:

```
════════════════════════════════════════════════════════════════════════
  MCP API KEY — COPY THIS NOW (shown once; stored in ./data/mcp_api_key)

  Bearer 7290f42b…

  .mcp.json:
    "headers": {"Authorization": "Bearer 7290f42b…"}

  Regenerate:  docker exec wmcp python src/mcp_keygen.py
════════════════════════════════════════════════════════════════════════

Registration: 3/3 ready
MCP server listening on http://0.0.0.0:6042/mcp (Streamable HTTP)
[tls] WDA TLS verification DISABLED — set WAGO_TLS_CA=... to enable.
[tls] MCP endpoint TLS DISABLED — set MCP_TLS_CERT + MCP_TLS_KEY to enable.
[audit] Hash chain seeded from existing audit log
```

> The two `[tls]` warnings are expected on a default install. See [TLS Configuration](#tls-configuration) to enable.

### 4. Verify

```bash
TOKEN="<your-api-key>"

curl -X POST http://localhost:6042/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"jsonrpc":"2.0","method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}},"id":1}'

# Health check (no token required)
curl http://localhost:6042/health
```

---

## API Key Management

The server resolves the MCP API key in priority order:

1. **Docker Secret** `/run/secrets/mcp_api_key` — highest trust, recommended for production
2. **Env var** `MCP_API_KEY` — dev override
3. **Persisted file** `./data/mcp_api_key` — auto-generated on first boot, survives container recreations via volume mount
4. **Auto-generate** — generates a new key if none of the above exist

**Regenerate the key:**
```bash
docker exec wmcp python src/mcp_keygen.py
docker restart wmcp   # pick up new key
```

**Use a Docker Secret instead:**
```bash
echo "$(openssl rand -hex 32)" > secrets/mcp_api_key.txt
chmod 600 secrets/mcp_api_key.txt
# Uncomment mcp_api_key in docker-compose.yml, then:
docker rm -f wmcp && docker compose up -d
```

---

## TLS Configuration

Both TLS legs are **opt-in**. The server starts without TLS and logs a startup warning for each disabled leg.

### WDA connections (server → PLC)

WAGO PLCs use HTTPS with self-signed certificates. Three options:

**Option A — Per-PLC cert pinning** *(recommended for self-signed certs)*
```bash
# Extract the cert from each PLC
openssl s_client -connect 192.168.1.10:443 </dev/null 2>/dev/null \
  | openssl x509 > secrets/plc_cert_192_168_1_10

# Declare the secret in docker-compose.yml, then restart
docker rm -f wmcp && docker compose up -d
```
The server detects `plc_cert_<ip_underscored>` Docker Secrets automatically — no extra env var needed.

**Option B — Private CA bundle** *(recommended for managed fleets)*
```env
WAGO_TLS_CA=/run/secrets/wago_ca.pem
```

**Option C — System trust store** *(only if PLC certs are CA-signed)*
```env
WAGO_TLS_CA=true
```

### MCP endpoint (client → server)

```bash
# Generate a self-signed cert for dev
openssl req -x509 -newkey rsa:4096 \
  -keyout secrets/mcp_tls_key.pem \
  -out secrets/mcp_tls_cert.pem \
  -days 365 -nodes -subj "/CN=wago-mcp"
chmod 600 secrets/mcp_tls_key.pem
```

Declare the secrets in `docker-compose.yml`, then set:

```env
MCP_TLS_CERT=/run/secrets/mcp_tls_cert
MCP_TLS_KEY=/run/secrets/mcp_tls_key
# MCP_TLS_KEY_PASSWORD=   # only if key is password-protected
```

When TLS is active, update your client URLs from `http://` to `https://`.

---

## Connecting Clients

### Claude Code / direct HTTP (`.mcp.json`)

Add to your project's `.mcp.json`:

```json
{
  "mcpServers": {
    "wago-plc": {
      "type": "http",
      "url": "http://localhost:6042/mcp",
      "headers": {
        "Authorization": "Bearer <your-api-key>"
      }
    }
  }
}
```

### Claude Desktop (Windows)

Claude Desktop uses stdio transport and cannot connect directly to an HTTP MCP server. A lightweight proxy bridges the gap.

Install prerequisites on the Windows machine:

```powershell
python -m pip install fastmcp httpx
```

Create `wago_proxy.py`:

```python
import os
from fastmcp import Client
from fastmcp.server import create_proxy

api_key = os.environ.get("WAGO_MCP_API_KEY", "")
url = "http://<MCP_SERVER_IP>:6042/mcp"
headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

client = Client(url)
mcp = create_proxy(client, name="wago-plc")
mcp.run(transport="stdio")
```

Add to `%APPDATA%\Claude\claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "wago-plc": {
      "command": "python",
      "args": ["C:\\path\\to\\wago_proxy.py"],
      "env": {
        "WAGO_MCP_API_KEY": "<your-api-key>"
      }
    }
  }
}
```

Fully quit and relaunch Claude Desktop. A hammer icon appears with the tool count.

### OpenClaw / other agents

```json
{
  "mcpServers": {
    "wago-plc": {
      "type": "url",
      "url": "http://<MCP_SERVER_IP>:6042/mcp",
      "headers": {
        "Authorization": "Bearer <your-api-key>"
      }
    }
  }
}
```

For legacy SSE transport set `TRANSPORT=sse` in `.env` and point at `/sse` instead of `/mcp`.

---

## Tool Reference

### Discovery

| Tool | Description |
|------|-------------|
| `list_plcs` | List all registered PLC IPs |
| `describe_plc(plc_ip)` | Capability counts + feature names + `device_class`, `expected_parameter_count`, `parameter_count_ok` (cached, no network call) |

### Parameters

| Tool | Description |
|------|-------------|
| `find_parameters(plc_ip, query, writeable_only, user_settings_only, limit)` | Search by keyword |
| `get_parameter(plc_ip, parameter_id)` | Read one value, enum labels resolved |
| `get_parameters_bulk(requests)` | Read one param from N PLCs in parallel |
| `set_parameters(plc_ip, parameters)` | Write one or more parameters (bulk PATCH) |

### Methods

| Tool | Description |
|------|-------------|
| `find_methods(plc_ip, query, limit)` | Search by keyword |
| `get_method(plc_ip, method_id)` | Fetch inArgs/outArgs schema |
| `invoke_method(plc_ip, method_id, arguments, wait)` | Execute (sync or async) |
| `get_method_run(plc_ip, method_id, run_id)` | Poll async run status |

### Watchlists

| Tool | Description |
|------|-------------|
| `create_watchlist(plc_ip, parameter_ids, timeout_seconds)` | Create server-side monitoring list |
| `read_watchlist(plc_ip, watchlist_id)` | Read current values (resets timeout) |
| `delete_watchlist(plc_ip, watchlist_id)` | Free watchlist before timeout |

### Example workflows

**Read firmware version from all PLCs in one call:**
```
get_parameters_bulk([
  {"plc_ip": "192.168.1.10", "parameter_id": "0-0-version-firmwareversion"},
  {"plc_ip": "192.168.1.11", "parameter_id": "0-0-version-firmwareversion"}
])
```

**Sync NTP time on a PLC:**
```
find_methods("192.168.1.10", "ntp")
→ ["0-0-ntpclient-updatetime"]

invoke_method("192.168.1.10", "0-0-ntpclient-updatetime", wait=True)
→ {"status": "done", "run_id": "1", "out_args": {}}
```

**Monitor IO values repeatedly:**
```
create_watchlist("192.168.1.10", ["param-a", "param-b"], timeout_seconds=300)
→ {"watchlist_id": "1", "parameters": [...]}

read_watchlist("192.168.1.10", "1")   # call repeatedly
delete_watchlist("192.168.1.10", "1") # cleanup
```

---

## Audit Log

Every write operation (`set_parameters`, `invoke_method`) is appended to `/app/audit.log` as a tamper-evident JSON line. Each entry includes a `prev` field — the SHA-256 of the previous entry — forming a hash chain:

```
Entry 1  {"ts":"…","action":"set_parameters",…,"prev":"0000…0000"}  ← genesis
            │  sha256
            ▼
Entry 2  {"ts":"…","action":"invoke_method",…,"prev":"a3f1…c2d8"}
            │  sha256
            ▼
Entry 3  {"ts":"…","action":"set_parameters",…,"prev":"7b2e…91fa"}
```

**Full example entry:**
```json
{"ts":"2026-06-12T09:14:22+00:00","action":"set_parameters","plc":"192.168.1.10","agent":"key-7290f42b","result":"ok","prev":"a3f1c2d8…","params":[{"id":"0-0-ntpclient-updateinterval","value":600}]}
```

The `agent` field is `key-<first 8 chars of API key>`, linking each write to the bearer token used.

**Tail the live log:**
```bash
docker exec wmcp tail -f /app/audit.log
```

**Verify chain integrity:**
```bash
docker exec wmcp python src/audit_verify.py
# → [PASS] Chain intact — 42 entries verified (/app/audit.log)

# For a rotated segment (supply the hash of the last line of the previous file):
docker exec wmcp python src/audit_verify.py --log /app/audit.log.1 --seed <hex>
```

Exit code `0` = chain intact. Exit code `1` = tampered or missing entries.

---

## Configuration Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `WAGO_PLC_HOSTS` | — | Comma-separated PLC IPs |
| `DEFAULT_PLC_USERNAME` | `admin` | Shared username |
| `DEFAULT_PLC_PASSWORD` | `wago` | Shared password (use Docker Secret instead) |
| `PLC_PASSWORDS_<ip_underscores>` | — | Per-PLC password override |
| `MCP_API_KEY` | — | Bearer token for `/mcp`; auto-generated if absent |
| `WAGO_TLS_CA` | — | WDA TLS: `false` (off), `true` (system CA), or path to CA bundle |
| `MCP_TLS_CERT` | — | Path to TLS cert for MCP endpoint (enables HTTPS when set with key) |
| `MCP_TLS_KEY` | — | Path to TLS private key for MCP endpoint |
| `MCP_TLS_KEY_PASSWORD` | — | Password for encrypted TLS private key (optional) |
| `AUDIT_LOG_FILE` | `/app/audit.log` | Audit log path inside container |
| `SYSLOG_HOST` | — | Syslog/SIEM receiver hostname or IP; enables audit forwarding when set |
| `SYSLOG_PORT` | `514` | Syslog receiver port |
| `SYSLOG_TCP` | `false` | `true` = TCP (reliable), `false` = UDP |
| `TRANSPORT` | `streamable-http` | `streamable-http` or `sse` |
| `HOST` | `0.0.0.0` | Bind address |
| `PORT` | `6042` | Listen port |
| `WAGO_TIMEOUT_SECONDS` | `30` | Per-PLC HTTP timeout in seconds (use 45 for CC100) |
| `WAGO_PAGE_LIMIT` | `500` | Pagination page size |
| `WAGO_MAX_CONCURRENT_REGISTRATIONS` | `5` | Parallel PLC init limit |
| `LOG_LEVEL` | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `LOG_FILE` | `/app/mcp_server.log` | Debug log path inside container |

---

## Requirements

- Docker 24+ with Compose v2
- WAGO PLC with WDx/WDA REST API enabled (firmware ≥ 03.x)
- Network route from Docker host to PLC subnets

For Claude Desktop proxy: Python 3.11+ and `fastmcp` on the client machine.

---

## Releases

Pre-built images are published on [Docker Hub](https://hub.docker.com/r/wagoalex/wago-plc-mcp-server). A CycloneDX SBOM is published alongside every release image. `docker compose up -d` pulls the latest automatically.

---

## Security & CRA Compliance

This project targets compliance with the EU Cyber Resilience Act (Regulation 2024/2847).

| Document | Purpose |
|----------|---------|
| [SECURITY.md](SECURITY.md) | Vulnerability reporting, patch SLA, support lifetime |
| [docs/threat-model.md](docs/threat-model.md) | STRIDE risk assessment |
| [docs/cra-compliance-matrix.md](docs/cra-compliance-matrix.md) | Annex I requirements → evidence mapping |
| [docs/eu-declaration-of-conformity.md](docs/eu-declaration-of-conformity.md) | CRA Article 28 self-declaration |
| [docs/technical-file.md](docs/technical-file.md) | CRA Article 31 technical file index |

---

## License

[Mozilla Public License 2.0](LICENSE)
