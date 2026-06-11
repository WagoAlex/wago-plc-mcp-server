[![Docker Hub](https://img.shields.io/docker/pulls/wagoalex/wago-plc-mcp-server)](https://hub.docker.com/r/wagoalex/wago-plc-mcp-server)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

# wago-plc-mcp-server

> MCP server that connects WAGO PLCs to LLM agents via the WDx/WDA REST API.

Ask an AI assistant to read sensor values, change configuration, trigger firmware updates, or monitor entire PLC fleets — with no custom code.

```
Claude Desktop / OpenClaw / any MCP client
        │  stdio or Streamable HTTP  +  Bearer token
        ▼
wago-plc-mcp-server  (Docker, port 6042)
        │  HTTPS / WDA REST API  +  Bearer token per PLC
        ▼
WAGO PLC fleet  (PFC200, PFC300, CC100, Edge Controller)
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
- **Fuzzy parameter search** — find parameters by keyword without knowing exact IDs
- **Dual transport** — Streamable HTTP (default) or SSE, switched via env var
- **Docker-first** — single container, host networking for routed PLC subnets

### Security (CRA Tier-1)

- **Bearer auth on `/mcp`** — auto-generated key persisted to `./data/`; Docker Secret and env var override; `/health` always exempt
- **WDA Bearer token auth** — credentials sent once per PLC at startup; all subsequent WDA calls use a cached Bearer token
- **Audit log** — every `set_parameters` and `invoke_method` call written as JSON to `/app/audit.log` with timestamp, agent ID, PLC, and result
- **Docker Secrets** — PLC passwords and the MCP API key can be mounted as secrets instead of env vars
- **CycloneDX SBOM** — generated automatically on every build via syft

---

## Quick Start

### 1. Clone and configure

```bash
git clone https://github.com/WagoAlex/wago-plc-mcp-server.git
cd wago-plc-mcp-server
cp _env .env
```

Edit `.env`:

```env
WAGO_PLC_HOSTS=192.168.1.10,192.168.1.11,192.168.1.12
DEFAULT_PLC_USERNAME=admin
DEFAULT_PLC_PASSWORD=wago
PORT=6042
WAGO_TIMEOUT_SECONDS=15     # use 45 for CC100
```

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

On first boot the server prints the auto-generated API key — **copy it now**:

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
```

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

## Connecting to Claude Desktop (Windows)

Install prerequisites on the Windows machine:

```powershell
python -m pip install fastmcp httpx
```

Create `wago_proxy.py` — the proxy injects the Bearer token so Claude Desktop can reach the authenticated server:

```python
import os, sys
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

---

## Connecting via `.mcp.json` (Claude Code / direct HTTP)

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

---

## Connecting to OpenClaw / other agents

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
| `describe_plc(plc_ip)` | Capability counts + feature names (cached, no network call) |

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

Every write operation is appended to `/app/audit.log` as a JSON line:

```json
{"ts":"2026-06-11T14:05:13+00:00","action":"set_parameters","plc":"192.168.1.10","agent":"key-7290f42b","result":"ok","params":[{"id":"0-0-ntpclient-updateinterval","value":600}]}
{"ts":"2026-06-11T14:05:56+00:00","action":"invoke_method","plc":"192.168.1.10","agent":"key-7290f42b","result":"done","method":"0-0-ntpclient-updatetime","args":{}}
```

```bash
docker exec wmcp tail -f /app/audit.log
```

The `agent` field is `key-<first 8 chars of API key>`, linking each write to the bearer token used.

---

## Configuration Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `WAGO_PLC_HOSTS` | — | Comma-separated PLC IPs |
| `DEFAULT_PLC_USERNAME` | `admin` | Shared username |
| `DEFAULT_PLC_PASSWORD` | `wago` | Shared password (use Docker Secret instead) |
| `PLC_PASSWORDS_<ip_underscores>` | — | Per-PLC password override |
| `MCP_API_KEY` | — | Bearer token for `/mcp`; auto-generated if absent |
| `AUDIT_LOG_FILE` | `/app/audit.log` | Audit log path inside container |
| `TRANSPORT` | `streamable-http` | `streamable-http` or `sse` |
| `HOST` | `0.0.0.0` | Bind address |
| `PORT` | `6042` | Listen port |
| `WAGO_TIMEOUT_SECONDS` | `10` | Per-PLC HTTP timeout (use 45 for CC100) |
| `WAGO_PAGE_LIMIT` | `500` | Pagination page size |
| `WAGO_MAX_CONCURRENT_REGISTRATIONS` | `5` | Parallel PLC init limit |
| `LOG_LEVEL` | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `LOG_FILE` | `/app/mcp_server.log` | Debug log path inside container |

---

## Building

```bash
# Dev build (bump patch version)
./build.sh --patch

# Build and start immediately
./build.sh --patch --start

# Bump major version, build, and push to Docker Hub
./build.sh --major --release

# Publish current version without bumping
./build.sh --release
```

A CycloneDX SBOM is generated automatically after every build via syft and written to `sbom-<version>.json`. `--release` archives a copy under `sbom/`.

---

## Networking

The container uses `network_mode: host` by default. This is required when PLCs are on routed subnets not directly reachable from a bridged Docker network.

If your PLCs are on the same subnet as the Docker host and you prefer bridge networking, edit `docker-compose.yml`:

```yaml
# Comment out:
# network_mode: host

# Uncomment:
ports:
  - "6042:6042"
networks:
  - wago-net
```

---

## Requirements

- Docker 24+ with Compose v2
- WAGO PLC with WDx/WDA REST API enabled (firmware ≥ 03.x)
- Network route from Docker host to PLC subnets

For Claude Desktop proxy: Python 3.11+ and `fastmcp` on the client machine.

---

## License

MIT
