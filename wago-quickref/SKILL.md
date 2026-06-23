---
name: wago-plc-mcp-server
description: |
  Use this skill whenever the user is working on the wago-plc-mcp-server project or any WAGO WDA-based MCP server. Triggers include: writing or fixing Python modules (main.py, wda_client.py, plc_manager.py, enricher.py, logging_config.py), configuring .env or docker-compose.yml for WAGO PLC deployments, debugging WDA REST API calls (pagination, POST vs PATCH, invoke_method, monitoring lists), writing deployment or health-check scripts, asking about FastMCP tool registration, transport config (SSE vs Streamable HTTP), Claude Desktop proxy setup, fleet-wide parameter reads, or firmware version management. Use this skill even when the request seems simple — e.g. "fix the set_parameters call" or "write a health check" — because WAGO WDA has non-obvious API behaviour that requires this reference to get right.
---

# WAGO PLC MCP Server Skill

## Project Overview

MCP server bridging WAGO PLCs (PFC200, PFC300, CC100, Edge Controller) to LLM agents via the WDx/WDA REST API. Agents can discover, read, write, and monitor PLC parameters using natural language.

- **Transport:** Streamable HTTP (default) or SSE (legacy)
- **Stack:** Python 3.14, FastMCP (`mcp` 1.27.1+), httpx, Docker
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
├── Dockerfile               # python:3.14-slim + uv
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
| `describe_plc` | Capability summary + `device_class`, `expected_parameter_count`, `parameter_count_ok` | No (cache) |
| `find_parameters` | Substring/fuzzy search, up to 255 results | No (cache) |
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

### Safety gates (`src/safety.py`) — enforced before every write/invoke

Three code-level gates defend against a rogue/hallucinating agent. None can be
talked out of by the agent.

1. **Dangerous-method denylist** — IDs whose segments start with `reboot`,
   `restart`, `factory`, `firmware`, `format` (`is_dangerous_method`, ASCII-folded
   + segment-matched, so `firmware-update` and zero-width tricks both match).
   - Live mode: **denied** unless the exact ID is in `WAGO_ALLOW_METHODS`.
   - GitOps mode: **proposed** with `requires_human: CRITICAL` + empty `approved_by`.
2. **Per-PLC read-only** — `WAGO_READONLY_HOSTS` (CSV) or a `# readonly` tag in
   `WAGO_PLC_HOSTS_FILE`. Listed PLCs reject `set_parameters` AND `invoke_method`
   in every mode. Computed by `compute_readonly_hosts()`, shared with `apply.py`.
3. **`apply.py` human-gate** — a dangerous op needs a non-empty `approved_by`
   (from the YAML or `WAGO_APPROVED_BY` CI env) or it refuses; every executed
   reconcile is appended to the audit chain (`src/audit.py`).

See `docs/gitops/README.md` "Safety model" and `tests/test_safety.py`.

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

**Pagination:** WDA hard-caps at 255 entries/page regardless of requested limit. Parameters
return in registration order (not alphabetical). Always include
`parameter-errors-as-data-attributes=true` for `/wda/parameters` — `_paginate()` injects
this automatically. Use `--data-urlencode` for `page[limit]`/`page[offset]` in curl —
literal bracket embedding is silently ignored causing an infinite page-0 loop.
```python
next_url = f"{path}?page[limit]=255&page[offset]=0"
while next_url:
    body = (await client.get(next_url)).json()
    page = body.get("data", [])
    items.extend(page)
    if len(page) < page_limit:
        break  # defensive: shorter-than-full page = last page
    next_url = body.get("links", {}).get("next")  # absent on last page
```

---

## Parameter Cheat Sheet (FW31, all device classes)

Zero `find_parameters` round-trips for these — copy the ID directly.

> **Not in WDA:** CPU load, memory usage, uptime — not exposed via WDA API at FW31.

### Identity (CC100 · PFC200 · PFC300 · Edge)

| Parameter ID | What it gives you | W? |
|---|---|---|
| `0-0-version-firmwareversion` | Full firmware string e.g. `04.09.01` | — |
| `0-0-version-softwarereleaseindex` | Build index (31) — use for firmware matrix | — |
| `0-0-identity-ordernumber` | Article / order number e.g. `0752-8303/…` | — |
| `0-0-identity-serialnumber` | Device serial number | — |

### Network (CC100 · PFC200 · PFC300 · Edge)

| Parameter ID | What it gives you | W? |
|---|---|---|
| `0-0-networking-hostname-currentname` | Current active hostname | — |
| `0-0-networking-hostname-customname` | Set a custom hostname | ✓ |
| `0-0-networking-bridges-1-ipconfiguration-currentaddresses` | Active IP address(es) on bridge 1 | — |
| `0-0-networking-bridges-1-ipconfiguration-currentdefaultgateway` | Active default gateway | — |
| `0-0-networking-dns-utilizeddnsservers` | Active DNS servers | — |
| `0-0-networking-dns-customdnsservers` | Set custom DNS servers | ✓ |

### Time / NTP (CC100 · PFC200 · PFC300 · Edge)

| Parameter ID | What it gives you | W? |
|---|---|---|
| `0-0-systemtime-local-now` | Current local time (ISO 8601); write to set clock | ✓ |
| `0-0-ntpclient-configuredtimeservers` | NTP server address(es) | ✓ |
| `0-0-ntpclient-istimeserveravailable` | NTP sync OK? (bool) | — |
| `0-0-ntpclient-enabled` | NTP client on/off | ✓ |

### CODESYS Runtime (CC100 · PFC200 · PFC300 · Edge)

| Parameter ID | What it gives you | W? |
|---|---|---|
| `0-0-codesys3-enabled` | Runtime enabled/disabled | ✓ |
| `0-0-codesys3-applications` | List of loaded applications | — |
| `0-0-codesys3-webserver-enabled` | CODESYS WebVisu server on/off | ✓ |

### System status (CC100 · PFC200 · PFC300 · Edge)

| Parameter ID | What it gives you | W? |
|---|---|---|
| `0-0-firmwareupdate-status` | Update state (idle / running / error) | — |
| `0-0-firmwareupdate-progress` | Update progress % | — |
| `0-0-reboot-status` | Reboot state; use `invoke_method` for actual reboot | — |
| `0-0-memorycard-isavailable` | SD card present | — |

### Edge / WP400 panel only

| Parameter ID | What it gives you | W? |
|---|---|---|
| `0-0-integratedwebbrowser-startpage` | Kiosk/Webvisu start URL | ✓ |
| `0-0-integratedwebbrowser-startpagefavorite` | Use a saved favourite as start page | ✓ |
| `0-0-integratedwebbrowser-favorites` | Stored browser favourites list | ✓ |

### Quick troubleshooting bundle (fleet-wide)

Use `get_parameters_bulk` with this set for a fast health snapshot across all PLCs.
Primary use: **one parameter × N PLCs** (e.g. firmware version from all 16 at once).
When reading N parameters from a single PLC, keep batches ≤ 8 — larger batches can
overload the PLC and return 500s even for valid parameter IDs.

```
0-0-version-firmwareversion
0-0-networking-hostname-currentname
0-0-networking-bridges-1-ipconfiguration-currentaddresses
0-0-ntpclient-istimeserveravailable
0-0-codesys3-enabled
0-0-firmwareupdate-status
```

All IDs above verified live on FW31 (Edge .124, CC100 .110, PFC200 .117, PFC300 .119).

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
