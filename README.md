# wago-plc-mcp-server

> MCP server that connects WAGO PLCs to LLM agents via the WDx/WDA REST API.

Ask an AI assistant to read sensor values, change configuration, trigger firmware updates, or monitor entire PLC fleets — with no custom code.

```
Claude Desktop / OpenClaw / any MCP client
        │  stdio or Streamable HTTP
        ▼
wago-plc-mcp-server  (Docker, port 6042)
        │  HTTPS / WDA REST API
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

---

## Quick Start

### 1. Clone and configure

```bash
git clone https://github.com/your-username/wago-plc-mcp-server.git
cd wago-plc-mcp-server
cp _env .env
```

Edit `.env`:

```env
WAGO_PLC_HOSTS=192.168.1.10,192.168.1.11,192.168.1.12
DEFAULT_PLC_USERNAME=admin
DEFAULT_PLC_PASSWORD=wago
TRANSPORT=streamable-http
PORT=6042
WAGO_TIMEOUT_SECONDS=15     # use 45 for CC100
```

### 2. Start

```bash
docker compose up -d
docker logs wmcp -f
```

Expected output:
```
Registration: 3/3 ready
MCP server listening on http://0.0.0.0:6042/mcp (Streamable HTTP)
StreamableHTTP session manager started
```

### 3. Verify

```bash
curl -X POST http://localhost:6042/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}},"id":1}'
```

---

## Connecting to Claude Desktop (Windows)

Claude Desktop requires a local stdio proxy. Install prerequisites on Windows:

```powershell
python -m pip install fastmcp
```

Create `wago_proxy.py`:

```python
from fastmcp import FastMCP, Client
from fastmcp.server import create_proxy

client = Client("http://<MCP_SERVER_IP>:6042/mcp")
mcp = create_proxy(client, name="wago-plc")
mcp.run(transport="stdio")
```

Add to `%APPDATA%\Claude\claude_desktop_config.json`:

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

Fully quit and relaunch Claude Desktop. A hammer icon appears with the tool count.

---

## Connecting to OpenClaw / other agents

Point directly at the SSE or Streamable HTTP endpoint:

```env
TRANSPORT=sse   # for OpenClaw
```

OpenClaw config:
```json
{
  "mcpServers": {
    "wago-plc": {
      "type": "url",
      "url": "http://<MCP_SERVER_IP>:6042/sse"
    }
  }
}
```

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

## Configuration Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `WAGO_PLC_HOSTS` | — | Comma-separated PLC IPs |
| `DEFAULT_PLC_USERNAME` | `admin` | Shared username |
| `DEFAULT_PLC_PASSWORD` | `wago` | Shared password |
| `PLC_PASSWORDS_<ip_with_underscores>` | — | Per-PLC password override |
| `TRANSPORT` | `streamable-http` | `streamable-http` or `sse` |
| `HOST` | `0.0.0.0` | Bind address |
| `PORT` | `6042` | Listen port |
| `WAGO_TIMEOUT_SECONDS` | `10` | Per-PLC HTTP timeout (use 45 for CC100) |
| `WAGO_PAGE_LIMIT` | `500` | Pagination page size |
| `WAGO_MAX_CONCURRENT_REGISTRATIONS` | `5` | Parallel PLC init limit |
| `LOG_LEVEL` | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `LOG_FILE` | `/app/mcp_server.log` | Log file path inside container |

---

## Building

```bash
# Dev build (patch version bump)
./build.sh --patch

# Build and start immediately
./build.sh --patch --start

# Release and push to Docker Hub
./build.sh --release
```

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
