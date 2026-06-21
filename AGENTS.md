# AGENTS.md — AI Agent Guide for wago-plc-mcp-server

This file is the authoritative context document for AI coding agents (Claude
Code, Codex, Copilot, Cursor, and similar). Read it before modifying any
file in this repository.

---

## What this project is

An **MCP server** that bridges a fleet of **WAGO PLCs** to LLM agents via
the WAGO **WDA/WDx REST API**. Agents discover, read, write, and monitor PLC
system parameters in natural language — no custom integration code required.

It is **not** a fieldbus gateway. It does not touch CODESYS program variables,
I/O tags, Modbus registers, or OPC-UA nodes. It manages the **system and
diagnostic layer** of WAGO controllers: firmware version, NTP, SSH, network
settings, service health, LED states, reboot/update actions.

Target hardware: CC100, PFC100 G2, PFC200 G2, PFC300, Edge Controller, WP400,
TP600 — firmware build >= 28.

---

## Repository map

```
src/
  main.py            FastMCP server entry point — all @mcp.tool definitions live here
  wda_client.py      Async WDA REST client (httpx + JSON:API pagination)
  plc_manager.py     PLC registry, parallel init, semaphore-bounded fan-out
  enricher.py        Enum resolution and parameter/method enrichment
  gitops.py          GitOps YAML helpers — desired_state_fragment(), ops_fragment(),
                     cloud_params(), ntp_params(), snmp_params(), serial_params(),
                     openvpn_params(), browser_params()
  logging_config.py  loguru setup + stdlib interception

scripts/
  apply.py           Reconciler: reads plcs/<ip>.yaml or ops/<id>.yaml,
                     diffs vs live PLC, applies drift — dry-run by default

docs/
  gitops/README.md   YAML schema blueprint for the wago-plc-config config repo
  *.json             Raw WDA parameter cassettes per device class (FW31)

wago-quickref/
  SKILL.md                         Contributor skill — WDA HTTP behaviour
  references/wda-api-reference.md  Full WDA endpoint and payload reference

wago-plc-skill/SKILL.md            End-user skill — natural-language tool mapping
wago-plc-agent-skill/SKILL.md      Autonomous agent skill — tool contracts, error shapes
```

---

## Architecture in one paragraph

`main.py` registers MCP tools via FastMCP (streamable-HTTP on port 6042,
bearer-auth required). Each tool call reaches `plc_manager.py`, which holds
an in-memory registry of `WDAClient` instances — one per PLC IP. `WDAClient`
(`wda_client.py`) speaks JSON:API over HTTPS to the PLC, handles pagination,
bearer-token auth, and retries. `enricher.py` resolves integer enum values to
human labels before results are returned to the agent. The `./data` volume
holds the mutable runtime state: API key, audit log, fleet host file.

---

## 13 MCP tools — quick reference

### Discovery

| Tool | Purpose |
|------|---------|
| `list_plcs` | Return all registered PLC IPs |
| `describe_plc(plc_ip)` | Capability counts, feature names, device_class, parameter count validation |

### Parameters

| Tool | Purpose |
|------|---------|
| `find_parameters(plc_ip, query, writeable_only, user_settings_only, limit)` | Keyword search — up to 100 results |
| `get_parameter(plc_ip, parameter_id)` | Read one value with enum labels resolved |
| `get_parameters_bulk(requests)` | Read one param from N PLCs in parallel |
| `set_parameters(plc_ip, parameters)` | Bulk PATCH — pre-validates writeability from cache |

### Methods

| Tool | Purpose |
|------|---------|
| `find_methods(plc_ip, query, limit)` | Keyword search on method IDs |
| `get_method(plc_ip, method_id)` | Fetch inArgs/outArgs schema |
| `invoke_method(plc_ip, method_id, arguments, wait)` | Execute sync or async |
| `get_method_run(plc_ip, method_id, run_id)` | Poll async run status |

### Watchlists

| Tool | Purpose |
|------|---------|
| `create_watchlist(plc_ip, parameter_ids, timeout_seconds)` | Register server-side polling list on PLC |
| `read_watchlist(plc_ip, watchlist_id)` | Fetch all current values in one request |
| `delete_watchlist(plc_ip, watchlist_id)` | Release watchlist immediately |

---

## WDA API — the shapes that bite

Read `wago-quickref/references/wda-api-reference.md` before touching any WDA
HTTP behaviour. Key rules:

- **Base URL:** `https://<IP>/wda` — HTTPS only, self-signed certs (`verify=False`).
- **Set parameters:** `PATCH /wda/parameters` with JSON:API body. `204` = success, empty body. POST returns 405.
- **Invoke method:** `POST /wda/methods/{id}/runs?result-behavior=sync` — each inArg wrapped as `{"value": ...}`, never flat.
- **Pagination:** Follow `links.next` until absent. WDA hard-caps at **255 entries per page** regardless of `page[limit]`. Also break when `len(page_data) < page_limit`.
- **URL encoding:** `page[limit]` and `page[offset]` **must** go through a query-param encoder — literal brackets in URL strings are silently ignored, causing an infinite page-0 loop.
- **Bulk reads:** Always include `parameter-errors-as-data-attributes=true` or one unreadable parameter will 500 the entire page.

---

## GitOps write-gate

`GITOPS_MODE=1` in `.env` intercepts all writes:
- `set_parameters` → returns `desired_state_fragment()` YAML for the agent to PR
- `invoke_method` → returns `ops_fragment()` YAML for the agent to PR

`GITOPS_MODE=0` (default) writes directly and appends to the audit log.

Config YAML schema: `docs/gitops/README.md`. Helpers: `src/gitops.py`.

### `gitops.py` helper index

| Helper | Signature | Subsystem |
|--------|-----------|-----------|
| `cloud_params(client_id, host, cloudtype, protocol)` | str, str, int=2, int=4 | Cloud/MQTT |
| `ntp_params(servers, update_interval)` | list[str], int=300 | NTP |
| `snmp_params(enabled, community, location, contact)` | bool, str, str, str | SNMP |
| `serial_params(assigned_mode, assigned_owner)` | int, int|None | Serial port |
| `openvpn_params(enabled, config_description, cert_description)` | bool, str, str | OpenVPN |
| `browser_params(startpage_mode, startpage_favorite)` | int=0, int=1 | HMI browser (WP400/TP600) |
| `desired_state_fragment(plc_ip, parameters)` | str, list[dict] | Generate desired-state YAML |
| `ops_fragment(plc_ip, method_id, arguments, agent_id)` | str, str, dict, str | Generate ops YAML |

---

## Fleet configuration

PLCs register at startup only — no MCP tool can add or remove them at
runtime. Fleet changes require editing `.env` or `./data/fleet.txt` and
restarting the container.

```env
WAGO_PLC_HOSTS=192.168.1.10,192.168.1.11    # CSV, no spaces
WAGO_PLC_HOSTS_FILE=/app/data/fleet.txt     # one IP per line, # comments ok
```

Per-PLC password override: `PLC_PASSWORDS_192_168_1_11=secret` (IP with
underscores). Do not re-introduce runtime fleet registration as an MCP tool.

---

## Hard rules — do not violate these

**NEVER:**
- `pip install` anything — the container is the only runtime; build via Docker.
- Read or print credentials — `.env`, `_env`, `secrets/` hold PLC passwords.
- Add an MCP tool that registers/deregisters PLCs at runtime — this was
  deliberately removed (v2.1.0). Dynamic fleet management requires human
  approval via the pending-queue pattern.
- Write TCP/IP, bridge, or Ethernet port configuration parameters — a wrong
  value takes a PLC offline and requires physical access to recover.
- Embed `page[limit]` or `page[offset]` literally in a URL string.
- Pass `description` or `transport` to the FastMCP constructor — it accepts
  only `name`, `instructions`, `host`, `port`.

**ALWAYS:**
- Read `wago-quickref/references/wda-api-reference.md` before changing any
  WDA HTTP call.
- Run tests inside Docker: `docker exec wmcp pytest tests/`.
- Tag commits: `fix:`, `feat:`, `chore:`, `docs:`.
- Bump `version.txt` and run `./build.sh` before publishing an image.

---

## Key known landmines

| Landmine | Detail |
|----------|--------|
| Healthcheck vs auth | `/health` must stay auth-exempt. Anything that adds bearer auth to `/mcp` must not also gate `/health`. |
| FastMCP constructor | `name`, `instructions`, `host`, `port` only. `description` or `transport` causes startup failure. |
| Watchlist kwarg names | `WDAClient` uses `timeout=` and `include_parameters=`, not `timeout_seconds=` or `include_values=`. Verify call sites match. |
| Boolean drift in `apply.py` | `str(False)` = `"False"` != `"false"`. The `_coerce()` function and `.lower()` comparisons handle this — do not remove them. |
| Cloud config code-41 | `cloudtype` and `transport-host` must be in the same PATCH. Always use `cloud_params()` which includes both. |
| Hung container | If logs show nothing since startup: `docker rm -f wmcp && docker compose up -d`. A plain restart won't help. |
| FW31 bacnet parameter | `bacnet-datalinks-1-sc-mode` returns an error on FW31. `_paginate()` injects `parameter-errors-as-data-attributes=true` automatically — do not remove it. |

---

## Device class — parameter counts (FW31 baseline)

| Class | Count | Key unique features |
|-------|-------|---------------------|
| CC100 | 360 | Compact; no serial WDA params |
| PFC200 Gen 2 | 398 | Serial port (`0-0-serialinterfaces-*`) |
| PFC300 | 393 | |
| Edge Controller | 394 | `0-0-plcruntime-*` CODESYS state params |
| TP600 | 410 | Full PLC+HMI; CODESYS3, BACnet, cloud, serial, display, browser, LED, acoustic |
| WP400 | 189 | Web panel only; no CODESYS/BACnet/I/O bus; display + browser params only |

`describe_plc` returns `expected_parameter_count` from this table and
`parameter_count_ok` (floor check: actual >= expected).

---

## Parameters NOT exposed via WDA

These must be configured through WAGO Web-Based Management (WBM):

- Syslog (remote log forwarding)
- Port mapping / firewall / iptables rules
- Commissioning service
- OpenVPN cert/key/config file upload (WDA exposes only descriptions + enable)
- Browser favorites list (WDA exposes only startpage mode)
- SNMP trap receiver configuration details

---

## Security model

| Layer | Mechanism |
|-------|-----------|
| MCP endpoint | Bearer token; auto-generated or Docker Secret; `/health` exempt |
| Rate limiting | 60 req/60 s per source IP; `429 Retry-After` |
| WDA connections | HTTP Basic → WDA Bearer token; cached, refreshed on 401 |
| Audit log | Tamper-evident JSON-lines with SHA-256 hash chain on `./data` volume |
| TLS — WDA | Off by default; `WAGO_TLS_CA` enables per-PLC cert pinning via Docker Secret |
| TLS — MCP | Off by default; `MCP_TLS_CERT` + `MCP_TLS_KEY` enables HTTPS on port 6042 |

Every `set_parameters` and `invoke_method` call is logged with timestamp,
parameter IDs, values, and the first 8 chars of the API key.

---

## Source-of-truth hierarchy

1. `src/` code + `wago-quickref/references/wda-api-reference.md` — authoritative.
2. `wago-quickref/SKILL.md` — accurate project skill; matches deployed transport.
3. Any external skill describing `aiohttp`, base `/wda/v2`, or `inputParameters`
   payloads is **stale** — the live client uses `httpx`, base `/wda`, JSON:API,
   and `/runs` for method invocation.

---

## Build / deploy quick reference

```bash
# Replace running container
docker rm -f wmcp && docker compose up -d --build
docker logs wmcp -f

# Version bump + build
./build.sh --patch           # patch bump, build, generate SBOM
./build.sh --patch --start   # + docker compose up
./build.sh --release         # build current version, push to Docker Hub, archive SBOM

# Tests inside container
docker exec wmcp pytest tests/
docker exec wmcp ruff check src/
```

Container name: `wmcp`. Image: `wagoalex/wago-plc-mcp-server:latest`.
Port: `6042`. Transport: streamable-HTTP at `/mcp`.

---

## Graphify knowledge graph

This project has a graphify knowledge graph at `graphify-out/`.

- Before answering architecture questions, read `graphify-out/GRAPH_REPORT.md`.
- If `graphify-out/wiki/index.md` exists, navigate it instead of reading raw files.
- For cross-module questions use `graphify query`, `graphify path`, or
  `graphify explain` rather than grep.
- After modifying source files, run `graphify update .` (AST-only, no API cost).
