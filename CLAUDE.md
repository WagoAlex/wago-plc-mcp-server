# wago-plc-mcp-server — Claude Code guide

MCP server bridging a fleet of WAGO PLCs to LLM agents via the WAGO **WDA/WDx REST
API**. Agents discover, read, write, and monitor PLC parameters in natural language.
Targets CC100 + PFC200/PFC300 + Edge Controller, deployed via Docker on a host
routed to the PLC subnets.

## Hard rules
- **Never `pip install` to run anything — always build/run via Docker.** The
  container is the only supported runtime.
- **Never read or print credentials.** `.env`, `_env`, and `secrets/` hold PLC
  passwords. Don't `cat` them.
- When touching WDA HTTP behaviour, read `wago-quickref/references/wda-api-reference.md`
  first — the API has non-obvious shapes (see "WDA REST API" below).

## Source-of-truth hierarchy (this project has docs that can drift)
1. **Code in `src/` + `wago-quickref/references/wda-api-reference.md`** — authoritative.
2. `wago-quickref/SKILL.md` — accurate project skill; matches the deployed
   streamable-HTTP architecture.
3. Any external "wago" skill describing `aiohttp`, base `/wda/v2`, or
   `inputParameters` payloads is **stale and wrong** — ignore it. The live client
   uses `httpx`, base `/wda`, JSON:API, and `/runs` for method invocation.

## Layout
```
src/
  main.py            FastMCP server + all @mcp.tool definitions; transport entry point
  wda_client.py      Async WDA REST client (httpx), JSON:API pagination
  plc_manager.py     PLC registry, parallel init, semaphore-bounded registration
  enricher.py        Enum resolution + parameter/method enrichment
  logging_config.py  loguru setup, stdlib interception
wago-quickref/
  SKILL.md                        project skill (transport, tools, deployment)
  references/wda-api-reference.md  full WDA endpoint + payload reference
wago_proxy.py        stdio<->HTTP proxy so Claude Desktop can reach the server
claude_desktop_config.json
.env / _env          runtime config / example (never commit .env)
docker-compose.yml   deployment (network_mode: host; /mcp healthcheck)
Dockerfile           python:3.12-slim + uv ; CMD ["python","src/main.py"]
build.sh             version bump + build + SBOM (+ optional push)
```

## Transport (verified against the running container)
Port **6042**, transport **streamable-HTTP at `/mcp`**. The docker-compose
healthcheck POSTs a JSON-RPC `initialize` to `/mcp` and treats `200` or `400`
("Missing session ID") as alive — a healthy container proves `/mcp` is serving.
`TRANSPORT=sse` in env switches to legacy SSE at `/sse`, but the running
deployment uses `/mcp`. Claude Code connects via `.mcp.json` as `type: http`.

## Build / run / redeploy
```bash
./build.sh --patch            # bump patch, build image, generate SBOM (syft present)
./build.sh --patch --start    # ...and docker compose up
./build.sh --patch --no-cache # after dependency changes
./build.sh --release          # build current version, push image, archive SBOM

# Replace the RUNNING container. A plain --build will NOT replace it because of
# restart: unless-stopped — remove it first:
docker rm -f wmcp && docker compose up -d --build
docker logs wmcp -f
docker ps | grep wmcp
```
Container **`wmcp`**. Image `wagoalex/wago-plc-mcp-server:latest`.

## Known landmines
- **T1 (auth) will break the current healthcheck.** Today the healthcheck's
  unauthenticated `initialize` probe to `/mcp` returns `400`. Once T1 adds bearer
  auth at the endpoint, the same probe returns `401` and the container goes
  unhealthy. T1 must add an **exempt `/health` route** and repoint the healthcheck
  at it.
- **Watchlist call sites — verify against live `src/main.py`.** An earlier snapshot
  had `main.py` calling `create_monitoring_list(..., timeout_seconds=, include_values=)`
  and `get_monitoring_list(..., include_values=)` while `wda_client.py` defines
  `timeout=` / `include_parameters=` and no `include_values` (→ `TypeError`).
  Confirm the kwargs match on both sides before relying on `create_watchlist` /
  `read_watchlist`.
- **"unhealthy" can be misleading.** If logs show nothing new since startup the
  server hung — `docker rm -f wmcp && docker compose up -d`, not `restart`.
- **FastMCP constructor** accepts `name`, `instructions`, `host`, `port` — passing
  `description` or `transport` to it causes startup failure.

## WDA REST API — the shapes that bite
- Base `https://<PLC_IP>/wda` — **HTTPS only** (HTTP -> 426). Self-signed certs
  (`verify=False`). Auth: HTTP Basic today. Accept/Content-Type
  `application/vnd.api+json`.
- **Set:** `PATCH /wda/parameters` (bulk) or `/wda/parameters/{id}`, body
  `{"data":[{"id","type":"parameters","attributes":{"value":...}}]}`. `204` =
  success, empty body. (POST -> 405.)
- **Invoke:** `POST /wda/methods/{id}/runs?result-behavior=sync`, body
  `{"data":{"type":"runs","attributes":{"inArgs":{name:{"value":...}}}}}`. Each
  inArg is wrapped `{"value":...}`, never flat.
- **Pagination:** follow `links.next` until absent (JSON:API). Never assume one page.
- `error_code` in error bodies is more specific than the HTTP status — look it up
  in `wago-quickref/references/wda-api-reference.md`.

## Config (.env)
`WAGO_PLC_HOSTS` (CSV, no spaces), `DEFAULT_PLC_USERNAME` / `DEFAULT_PLC_PASSWORD`,
`HOST`, `PORT=6042`, `TRANSPORT`, `WAGO_TIMEOUT_SECONDS` (CC100 needs 45+;
PFC200/300 ~ 15), `WAGO_PAGE_LIMIT=500`, `WAGO_MAX_CONCURRENT_REGISTRATIONS=5`,
`LOG_LEVEL`, `LOG_FILE`.

## Tests
No automated tests in the repo yet. Validate manually against live PLCs (curl
recipes in the WDA reference) or via the connected `wago-plc` MCP server (see
`.mcp.json`). When adding tests, mock `httpx` at the `WDAClient` boundary.

## CRA hardening roadmap
Tier-1 tasks T1-T5 (API-key middleware, Docker secrets, WDA bearer-token auth,
write-audit log, SBOM). T5 (SBOM in `build.sh`) is done. When T1 lands, add the
`Authorization` header to `.mcp.json` and add the exempt `/health` route (above).

## SBOM
`build.sh` generates a CycloneDX SBOM `sbom-<version>.json` (gitignored) via syft
after build; `--release` archives a copy under `sbom/`. NOTE: a manually-named
`sbom.json` already exists at root — the gitignore pattern `/sbom-*.json` does NOT
match it; broaden to `/sbom*.json` if you want it ignored too.

## graphify

This project has a graphify knowledge graph at graphify-out/.

Rules:
- Before answering architecture or codebase questions, read graphify-out/GRAPH_REPORT.md for god nodes and community structure
- If graphify-out/wiki/index.md exists, navigate it instead of reading raw files
- For cross-module "how does X relate to Y" questions, prefer `graphify query "<question>"`, `graphify path "<A>" "<B>"`, or `graphify explain "<concept>"` over grep — these traverse the graph's EXTRACTED + INFERRED edges instead of scanning files
- After modifying code files in this session, run `graphify update .` to keep the graph current (AST-only, no API cost)
