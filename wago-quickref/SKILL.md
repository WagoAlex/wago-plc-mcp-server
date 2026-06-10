---
name: wago-plc-mcp-server
description: |
  Use this skill whenever the user is working on the wago-plc-mcp-server project or any WAGO WDA-based MCP server. Triggers include: writing or fixing Python modules (main.py, wda_client.py, plc_manager.py, enricher.py, logging_config.py), configuring .env or docker-compose.yml for WAGO PLC deployments, debugging WDA REST API calls (pagination, POST vs PATCH, invoke_method, monitoring lists), writing deployment or health-check scripts, asking about FastMCP tool registration, transport config (SSE vs Streamable HTTP), Claude Desktop proxy setup, fleet-wide parameter reads, or firmware version management. Use this skill even when the request seems simple — e.g. "fix the set_parameters call" or "write a health check" — because WAGO WDA has non-obvious API behaviour that requires this reference to get right.
---

# WAGO PLC MCP Server Skill

## Project Overview

MCP server bridging WAGO PLCs (PFC200, PFC300, CC100, Edge Controller) to LLM agents via the WDx/WDA REST API. Agents can discover, read, write, and monitor PLC parameters using natural language.

- **Transport:** Streamable HTTP (default) or SSE (legacy)
- **Stack:** Python 3.12, FastMCP (`mcp` 1.27.1+), httpx, Docker
- **Port:** 6042
- **Container name:** `wmcp`
- **Image:** `wagoalex/wago-plc-mcp-server:latest`

---

## Project Structure

```
wago-plc-mcp-server/
├── src/
│   ├── main.py              # FastMCP server, all tool definitions, transport entry point
│   ├── wda_client.py        # Async WDA REST client (httpx), JSON:API pagination
│   ├── plc_manager.py       # PLC registry, parallel init, semaphore-bounded concurrency
│   ├── enricher.py          # Enum resolution, parameter enrichment helpers
│   └── logging_config.py    # loguru structured logging, stdlib interception
├── .env                     # Runtime config (never commit)
├── docker-compose.yml       # Production deployment
├── Dockerfile               # python:3.12-slim + uv
├── pyproject.toml           # Dependencies
└── build.sh                 # Version bump + build + optional push
```

---

## Transport Configuration

Switch transport via `TRANSPORT` env var — no code change needed:

```env
TRANSPORT=streamable-http   # default — Claude Desktop, modern MCP clients
TRANSPORT=sse               # legacy — OpenClaw, older agents
```

**FastMCP constructor — required settings:**
```python
mcp = FastMCP(
    name="wago-plc-mcp",
    host=os.getenv("HOST", "0.0.0.0"),
    port=int(os.getenv("PORT", "6042")),
    transport_security=None,   # disables DNS rebinding protection
                               # REQUIRED for LAN clients not on localhost
)
```

**Entry point pattern in `main()`:**
```python
transport = os.getenv("TRANSPORT", "streamable-http").strip().lower()
if transport == "sse":
    run_fn = mcp.run_sse_async        # serves /sse
else:
    run_fn = mcp.run_streamable_http_async  # serves /mcp
await run_fn()
```

Streamable HTTP request sequence per tool call:
```
POST /mcp   → 200 (init, returns mcp-session-id header)
POST /mcp   → 202 (tool call accepted)
GET  /mcp   → 200 (SSE stream, returns result)
POST /mcp   → 200 (ack)
DELETE /mcp → 200 (session teardown)
```

---

## Claude Desktop Integration

Claude Desktop only supports stdio transport. Use a FastMCP proxy script as a bridge.

**`wago_proxy.py`** (on the Windows client machine):
```python
from fastmcp import FastMCP, Client
from fastmcp.server import create_proxy

client = Client("http://<MCP_SERVER_IP>:6042/mcp")
mcp = create_proxy(client, name="wago-plc")
mcp.run(transport="stdio")
```

**`claude_desktop_config.json`** (`%APPDATA%\Claude\` on Windows):
```json
{
  "mcpServers": {
    "wago-plc": {
      "command": "python",
      "args": ["C:\\path\\to\\wago_proxy.py"]
    }
  }
}
```

Install on Windows: `python -m pip install fastmcp` (requires Python 3.11+, fastmcp 3.4+).

**Do NOT use `FastMCP.as_proxy()`** — deprecated since fastmcp 3.x. Use `create_proxy()` from `fastmcp.server`.

**Why not `type: "url"`?** Claude Desktop's `type: "url"` requires HTTPS + OAuth 2.1. Plain HTTP LAN addresses are silently rejected regardless of Claude Desktop version.

---

## Docker Deployment

```yaml
services:
  wago-plc-mcp-server:
    network_mode: host      # required when PLCs are on routed subnets
    healthcheck:
      test: ["CMD-SHELL", "curl -sf --max-time 2 -X POST http://localhost:6042/mcp -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' -d '{\"jsonrpc\":\"2.0\",\"method\":\"initialize\",\"params\":{\"protocolVersion\":\"2025-11-25\",\"capabilities\":{},\"clientInfo\":{\"name\":\"healthcheck\",\"version\":\"1.0\"}},\"id\":1}' | grep -qE '200|400'"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 15s
```

The healthcheck accepts both 200 and 400 — a 400 ("Missing session ID") means the server is alive and correctly rejecting a stateless probe.

**Build cycle:**
```bash
docker rm -f wmcp && docker compose up -d --build
docker logs wmcp -f
```

Always `rm -f` before rebuild. `restart: unless-stopped` keeps the old container alive — `--build` alone does not replace it.

---

## Configuration (.env)

```env
WAGO_PLC_HOSTS=192.168.1.10,192.168.1.11    # comma-separated, no spaces
DEFAULT_PLC_USERNAME=admin
DEFAULT_PLC_PASSWORD=wago
# PLC_PASSWORDS_192_168_1_10=custom_password  # per-PLC override

TRANSPORT=streamable-http
HOST=0.0.0.0
PORT=6042

WAGO_TIMEOUT_SECONDS=45     # CC100 ARM needs 45+; PFC200/PFC300 use 15
WAGO_PAGE_LIMIT=500
WAGO_MAX_CONCURRENT_REGISTRATIONS=5

LOG_LEVEL=INFO
LOG_FILE=/app/mcp_server.log
```

---

## Tool Reference (13 tools)

| Tool | Purpose | Network? |
|------|---------|---------|
| `list_plcs` | List registered PLC IPs | No (cache) |
| `describe_plc` | Capability summary | No (cache) |
| `find_parameters` | Substring/fuzzy search | No (cache) |
| `get_parameter` | Read one parameter | Yes |
| `get_parameters_bulk` | Read one param from N PLCs in parallel | Yes × N concurrent |
| `set_parameters` | Bulk PATCH, pre-validates writeability | Yes |
| `find_methods` | Search method IDs | No (cache) |
| `get_method` | Fetch inArgs/outArgs schema | Yes |
| `invoke_method` | Execute method (sync or async) | Yes |
| `get_method_run` | Poll async method run | Yes |
| `create_watchlist` | Server-side monitoring list | Yes |
| `read_watchlist` | Read watchlist values (resets timeout) | Yes |
| `delete_watchlist` | Free watchlist before timeout | Yes |

### `get_parameters_bulk` — fleet-wide parallel reads

Reduces N tool calls to 1. Use whenever reading the same parameter from multiple PLCs.

```json
[
  {"plc_ip": "192.168.42.110", "parameter_id": "0-0-version-firmwareversion"},
  {"plc_ip": "192.168.42.111", "parameter_id": "0-0-version-firmwareversion"}
]
```

Returns list of enriched dicts. Per-PLC failures return `{"plc_ip": ..., "error": ...}` without aborting the batch.

### Watchlists — correct call signatures (historically wrong)

```python
# CREATE — kwarg is "timeout", NOT "timeout_seconds"
await plc.client.create_monitoring_list(parameter_ids, timeout=timeout_seconds)

# READ — kwarg is "include_parameters", NOT "include_values"
await plc.client.get_monitoring_list(watchlist_id, include_parameters=True)
```

---

## WDA REST API — Critical Patterns

```
Base: https://<PLC_IP>/wda    (HTTP returns 426)
Auth: Authorization: Basic <base64(user:pass)>
Accept: application/vnd.api+json
Content-Type: application/vnd.api+json  (writes only)
```

**PATCH payload (set_parameters):**
```python
{"data": [{"id": pid, "type": "parameters", "attributes": {"value": value}}]}
# 204 = success with empty body
```

**Method invocation:**
```python
# POST /wda/methods/{mid}/runs?result-behavior=sync
{"data": {"type": "runs", "attributes": {"inArgs": {name: {"value": val}}}}}
# each inArg is {"value": ...} — NOT flat
```

**Pagination:**
```python
next_url = f"{path}?page[limit]={limit}&page[offset]=0"
while next_url:
    body = (await client.get(next_url)).json()
    items.extend(body.get("data", []))
    next_url = body.get("links", {}).get("next")  # absent on last page
```

---

## Firmware Version Reference
| Firmware Version | Firmware Index |
| ---------------- | -------------- |
| 04.09.01         | 31             |
| 04.08.14         | 30             |
| 04.08.12         | 30             |
| 04.08.09         | 30             |
| 04.07.51         | 29             |
| 04.07.50         | 29             |
| 04.07.03         | 29             |
| 04.06.07         | 28             |
| 04.06.03         | 28             |
| 04.06.01         | 28             |



Parameter: `0-0-version-firmwareversion` · Latest: **04.09.01 (index 31)**

---

## Debugging Guide

| Symptom | Root Cause | Fix |
|---------|-----------|-----|
| Logs show `/sse` despite `TRANSPORT=streamable-http` | Old `main.py` in image | Replace file on disk, then `docker rm -f wmcp && docker compose up -d --build` |
| Healthcheck 406 | Wrong Accept header | Add `-H 'Accept: application/json, text/event-stream'` |
| Healthcheck 400 | Stateless probe, no session ID | Normal — accept 400 as healthy |
| LAN client 421 / refused | `transport_security` not disabled | Add `transport_security=None` to FastMCP constructor |
| `unexpected keyword 'timeout_seconds'` | Wrong kwarg in `create_monitoring_list` | Use `timeout=` |
| `read_watchlist` empty parameters | Wrong kwarg in `get_monitoring_list` | Use `include_parameters=True` |
| Claude Desktop "not valid MCP config" | `type: "url"` needs HTTPS + OAuth | Use proxy script with stdio transport |
| `FastMCP.as_proxy()` deprecation | Removed in fastmcp 3.x | Use `create_proxy()` from `fastmcp.server` |
| CC100 registration timeout | Slow ARM WDA | `WAGO_TIMEOUT_SECONDS=45` |
| `--build` has no effect | Old container still running | `docker rm -f wmcp` first |
