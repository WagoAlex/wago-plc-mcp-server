"""WAGO PLC MCP Server — optimized for OpenClaw agents (small local models).

12 tools, compact responses, smart pre-validation.
"""
import asyncio
import json
import os
from difflib import get_close_matches
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from loguru import logger
from mcp.server.fastmcp import FastMCP, Context
from mcp.server.fastmcp.prompts import base

from logging_config import setup_logging, setup_audit_logging
from plc_manager import PLCManager, KNOWN_PARAM_COUNTS
from enricher import enrich_parameter, enrich_method_definition, parse_watchlist_response
from audit import DEFAULT_AUDIT_LOG, GENESIS, build_entry, read_prev_hash
from auth import AuthMiddleware, print_key_banner, resolve_api_key
from config import parse_plcs_from_env, resolve_tls_verify
from safety import compute_readonly_hosts, is_dangerous_method, parse_allowed_methods

# ───────────────────────── Bootstrap ─────────────────────────

load_dotenv()
setup_logging(
    log_file=os.getenv("LOG_FILE"),
    level=os.getenv("LOG_LEVEL", "INFO"),
)
setup_audit_logging(
    audit_log_file=os.getenv("AUDIT_LOG_FILE"),
    syslog_host=os.getenv("SYSLOG_HOST") or None,
    syslog_port=int(os.getenv("SYSLOG_PORT", "514")),
    syslog_tcp=os.getenv("SYSLOG_TCP", "").lower() in {"1", "true"},
)

plc_manager = PLCManager(
    timeout_seconds=float(os.getenv("WAGO_TIMEOUT_SECONDS", "45")),
    page_limit=int(os.getenv("WAGO_PAGE_LIMIT", "500")),
    max_concurrent_registrations=int(os.getenv("WAGO_MAX_CONCURRENT_REGISTRATIONS", "5")),
    ssl_verify=resolve_tls_verify(),
)

mcp = FastMCP(
    name="wago-plc-mcp",
    instructions=(
        "WAGO PLC access via WDx REST API. "
        "Workflow: list_plcs → describe_plc → find_parameters/find_methods → "
        "get_parameter/get_method → set_parameters/invoke_method. "
        "Use watchlists for repeated polling."
    ),
    host=os.getenv("HOST", "0.0.0.0"),
    port=int(os.getenv("PORT", "6042")),
)

FIND_LIMIT_MAX = 255
FIND_LIMIT_DEFAULT = 20

_AGENT_ID: str = "unknown"
_AUDIT_PREV_HASH: str = GENESIS  # seeded from last log line on startup
_GITOPS_MODE: bool = os.getenv("GITOPS_MODE", "").lower() in {"1", "true"}
_GITOPS_REPO: str = os.getenv("WAGO_GITOPS_REPO", "wago-plc-config")

# ───────────────────────── Safety gates ─────────────────────────
# See safety.py + docs/gitops/README.md "Safety model". Read-only hosts merge the
# WAGO_READONLY_HOSTS env with any `# readonly`-tagged lines in the fleet file.
_ALLOWED_METHODS: frozenset[str] = parse_allowed_methods(os.getenv("WAGO_ALLOW_METHODS"))
_READONLY_HOSTS: frozenset[str] = compute_readonly_hosts()

# Make a deliberately-opened dangerous path loud at startup.
for _m in _ALLOWED_METHODS:
    if is_dangerous_method(_m):
        logger.warning(f"[safety] WAGO_ALLOW_METHODS re-enables DANGEROUS method for live use: {_m}")
if _READONLY_HOSTS:
    logger.info(f"[safety] Read-only PLCs (writes/invokes refused): {sorted(_READONLY_HOSTS)}")


# ───────────────────────── Helpers ─────────────────────────

def _audit_log(action: str, plc_ip: str, details: dict, result: str) -> None:
    global _AUDIT_PREV_HASH
    line, _AUDIT_PREV_HASH = build_entry(action, plc_ip, _AGENT_ID, result, _AUDIT_PREV_HASH, details)
    logger.log("AUDIT", line)


def _seed_audit_hash(audit_log_path: str) -> None:
    """Seed _AUDIT_PREV_HASH from the last entry of an existing audit log (see audit.read_prev_hash)."""
    global _AUDIT_PREV_HASH
    if not audit_log_path.startswith("/app/data/"):
        logger.warning(
            f"[audit] AUDIT_LOG_FILE={audit_log_path} is not on the /app/data volume - "
            f"the tamper-evident chain will be LOST on container removal"
        )
    _AUDIT_PREV_HASH = read_prev_hash(audit_log_path)
    if _AUDIT_PREV_HASH != GENESIS:
        logger.info("[audit] Hash chain seeded from existing audit log")
    elif Path(audit_log_path).exists():
        logger.warning(f"[audit] {audit_log_path} exists but yielded genesis — empty/corrupt/partial write; starting fresh")


def _require_plc(ip: str):
    plc = plc_manager.get(ip)
    if not plc:
        return None, {
            "error": f"PLC {ip} not registered. Available: {plc_manager.list_ips()}"
        }
    return plc, None


def _score(text: str, query: str) -> int:
    """Higher is better. 0 means no match."""
    if not query:
        return 1
    q = query.lower()
    t = text.lower()
    if q == t:
        return 1000
    if t.startswith(q):
        return 100
    return 10 if q in t else 0


def _filter_search(items: set[str], query: str, limit: int) -> list[str]:
    """Substring + fuzzy fallback. Returns top-N IDs."""
    limit = min(max(1, limit), FIND_LIMIT_MAX)
    if not query:
        return sorted(items)[:limit]
    scored = [(i, _score(i, query)) for i in items]
    hits = [i for i, s in scored if s > 0]
    if not hits:
        # Fuzzy fallback
        hits = get_close_matches(query, items, n=limit, cutoff=0.5)
    else:
        hits.sort(key=lambda i: (-_score(i, query), i))
    return hits[:limit]


# ───────────────────────── MCP Resource ─────────────────────────

@mcp.resource("wago://catalog")
def wago_catalog() -> str:
    """Overview of all registered WAGO PLCs and their capability counts. Read this first."""
    if not plc_manager.list_ips():
        return "No PLCs registered. Check startup logs."
    lines = ["# WAGO PLC Catalog\n"]
    for ip in plc_manager.list_ips():
        plc = plc_manager.get(ip)
        lines.append(
            f"- **{ip}**: {len(plc.parameters)} parameters "
            f"({len(plc.param_writeable)} writeable), "
            f"{len(plc.methods)} methods, "
            f"{len(plc.features)} features, "
            f"{len(plc.devices)} devices, "
            f"{len(plc.enum_cases)} enums"
        )
    return "\n".join(lines)


# ───────────────────────── Tools: discovery ─────────────────────────

@mcp.tool()
async def list_plcs(ctx: Context) -> dict:
    """List all reachable WAGO PLCs. Use first to find a target IP."""
    return {"plcs": plc_manager.list_ips()}


@mcp.tool()
async def get_plc_audit_log(
    ctx: Context,
    plc_ip: str = "",
    action: str = "",
    limit: int = 50,
) -> dict:
    """Return recent audit log entries, newest first.

    plc_ip: filter to a specific PLC IP (empty = all PLCs).
    action: filter by action type — register_plc, deregister_plc, set_parameters,
            invoke_method (empty = all actions).
    limit: max entries to return (default 50, max 500).

    Each entry contains: ts, action, plc, agent, result, prev (chain hash),
    plus action-specific fields.
    """
    limit = min(max(1, limit), 500)
    audit_path = Path(os.getenv("AUDIT_LOG_FILE", DEFAULT_AUDIT_LOG))

    if not audit_path.exists():
        return {"entries": [], "total": 0, "note": "Audit log not yet created"}

    try:
        with audit_path.open("rb") as f:
            f.seek(0, 2)
            size = f.tell()
            read_size = min(size, 65536)  # 64 KB tail — covers 200+ entries at typical sizes
            f.seek(-read_size, 2)
            tail = f.read().decode("utf-8", errors="replace")
    except OSError as e:
        return {"error": f"Could not read audit log: {e}"}

    entries = []
    for line in tail.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if plc_ip and entry.get("plc") != plc_ip:
            continue
        if action and entry.get("action") != action:
            continue
        entries.append(entry)

    # Take the last `limit` chronological entries, return newest first
    entries = entries[-limit:][::-1]
    result: dict = {"entries": entries, "total": len(entries)}
    if plc_ip or action:
        result["filtered_by"] = {k: v for k, v in {"plc_ip": plc_ip, "action": action}.items() if v}
    return result


@mcp.tool()
async def describe_plc(ctx: Context, plc_ip: str) -> dict:
    """Get capability summary for a PLC: counts + feature names. Cheap, cached."""
    plc, err = _require_plc(plc_ip)
    if err:
        return err
    actual = len(plc.parameters)
    expected = KNOWN_PARAM_COUNTS.get(plc.device_class) if plc.device_class else None
    return {
        "ip": plc_ip,
        "device_name": plc.device_name,
        "device_class": plc.device_class,
        "parameter_count": actual,
        "expected_parameter_count": expected,
        # Floor, not exact match: WDA exposes dynamic instance parameters
        # (e.g. SNMP/Communities/N/*) only when that instance is configured,
        # so a unit with extra runtime config legitimately reports more
        # parameters than the FW31 reference baseline. Fewer than expected
        # still flags a real problem (incomplete sweep, wrong device class).
        "parameter_count_ok": actual >= expected if expected is not None else None,
        "writeable_parameter_count": len(plc.param_writeable),
        "user_setting_parameter_count": len(plc.param_user_setting),
        "device_count": len(plc.devices),
        "feature_count": len(plc.features),
        "method_count": len(plc.methods),
        "enum_count": len(plc.enum_cases),
        "features": sorted(plc.features),
    }


# ───────────────────────── Tools: parameters ─────────────────────────

@mcp.tool()
async def find_parameters(
    ctx: Context,
    plc_ip: str,
    query: str = "",
    writeable_only: bool = False,
    user_settings_only: bool = False,
    limit: int = FIND_LIMIT_DEFAULT,
) -> dict:
    """Search parameter IDs by substring/fuzzy match. Returns up to `limit` matches (default 20, max 255).

    Set writeable_only=True to filter parameters that can be written.
    Set user_settings_only=True to filter user-configurable parameters.
    Empty query returns the first N parameters alphabetically.
    """
    plc, err = _require_plc(plc_ip)
    if err:
        return err

    pool = plc.parameters
    if writeable_only:
        pool = pool & plc.param_writeable
    if user_settings_only:
        pool = pool & plc.param_user_setting

    matches = _filter_search(pool, query, limit)
    return {
        "matches": matches,
        "total_in_pool": len(pool),
        "truncated": len(matches) >= min(limit, FIND_LIMIT_MAX) and len(pool) > limit,
    }


@mcp.tool()
async def get_parameter(ctx: Context, plc_ip: str, parameter_id: str) -> dict:
    """Read a single parameter value. Resolves enum values to human-readable labels."""
    plc, err = _require_plc(plc_ip)
    if err:
        return err

    if parameter_id not in plc.parameters:
        matches = get_close_matches(parameter_id, plc.parameters, n=3, cutoff=0.6)
        return {
            "error": f"Unknown parameter '{parameter_id}'"
            + (f". Did you mean: {', '.join(matches)}?" if matches else "")
        }

    try:
        attrs = await plc.client.get_parameter(parameter_id)
    except Exception as e:
        logger.error(f"[{plc_ip}] get_parameter({parameter_id}) failed: {e}")
        return {"error": str(e)}

    return enrich_parameter(plc, parameter_id, attrs)


@mcp.tool()
async def get_parameters_bulk(
    ctx: Context,
    requests: list[dict],
) -> list[dict]:
    """Read one parameter from multiple PLCs in parallel — one call instead of N.

    requests: list of {"plc_ip": str, "parameter_id": str}
    Returns:  list of {"plc_ip": str, "parameter_id": str, "value": ..., ...} or {"error": ...}

    Concurrency is bounded by WAGO_MAX_CONCURRENT_READS (default 10) so a large
    request list cannot overload slow PLCs (CC100 web server is easily starved).

    Example — read firmware version from all PLCs:
    [{"plc_ip": "192.168.42.110", "parameter_id": "0-0-version-firmwareversion"}, ...]
    """
    sem = asyncio.Semaphore(int(os.getenv("WAGO_MAX_CONCURRENT_READS", "10")))

    async def _fetch(req: dict) -> dict:
        ip = req.get("plc_ip", "")
        pid = req.get("parameter_id", "")
        plc, err = _require_plc(ip)
        if err:
            return {"plc_ip": ip, "parameter_id": pid, "error": err["error"]}
        if pid not in plc.parameters:
            return {"plc_ip": ip, "parameter_id": pid, "error": f"Unknown parameter '{pid}'"}
        try:
            async with sem:
                attrs = await plc.client.get_parameter(pid)
            result = enrich_parameter(plc, pid, attrs)
            result["plc_ip"] = ip
            result["parameter_id"] = pid
            return result
        except Exception as e:
            return {"plc_ip": ip, "parameter_id": pid, "error": str(e)}

    return list(await asyncio.gather(*[_fetch(r) for r in requests]))


@mcp.tool()
async def set_parameters(
    ctx: Context, plc_ip: str, parameters: list[dict]
) -> dict:
    """Write multiple parameters in one PATCH call. Pre-validates writeability from cache.

    parameters: list of {"id": str, "value": any}
    Example: [{"id": "0-0-systemtime-local-now", "value": "2026-05-13T14:30:00"}]
    """
    plc, err = _require_plc(plc_ip)
    if err:
        return err

    if plc_ip in _READONLY_HOSTS:
        _audit_log("set_parameters", plc_ip, {"params": parameters}, "refused: read-only host")
        return {"error": f"PLC {plc_ip} is read-only (WAGO_READONLY_HOSTS / fleet.txt '# readonly'); writes refused."}

    unknown = [p.get("id") for p in parameters if p.get("id") not in plc.parameters]
    if unknown:
        return {"error": f"Unknown parameter IDs: {unknown}"}

    read_only = [p["id"] for p in parameters if p["id"] not in plc.param_writeable]
    if read_only:
        return {"error": f"Read-only parameter IDs (cannot be set): {read_only}"}

    if _GITOPS_MODE:
        from gitops import desired_state_fragment
        return desired_state_fragment(plc_ip, parameters, repo=_GITOPS_REPO)

    try:
        result = await plc.client.set_parameters(parameters)
        logger.info(f"[{plc_ip}] set {len(parameters)} parameter(s)")
        _audit_log("set_parameters", plc_ip, {"params": parameters}, "ok")
        return {"status": "ok", "result": result}
    except Exception as e:
        logger.error(f"[{plc_ip}] set_parameters failed: {e}")
        _audit_log("set_parameters", plc_ip, {"params": parameters}, f"error: {e}")
        return {"error": str(e)}


# ───────────────────────── Tools: methods ─────────────────────────

@mcp.tool()
async def find_methods(
    ctx: Context, plc_ip: str, query: str = "", limit: int = FIND_LIMIT_DEFAULT
) -> dict:
    """Search method IDs by substring/fuzzy match. Returns up to `limit` matches (default 20)."""
    plc, err = _require_plc(plc_ip)
    if err:
        return err

    matches = _filter_search(plc.methods, query, limit)
    return {
        "matches": matches,
        "total": len(plc.methods),
        "truncated": len(matches) >= min(limit, FIND_LIMIT_MAX) and len(plc.methods) > limit,
    }


@mcp.tool()
async def get_method(ctx: Context, plc_ip: str, method_id: str) -> dict:
    """Get method metadata with inline inArgs/outArgs signatures. One call gives the full schema needed for invoke_method."""
    plc, err = _require_plc(plc_ip)
    if err:
        return err
    if method_id not in plc.methods:
        matches = get_close_matches(method_id, plc.methods, n=3, cutoff=0.6)
        return {
            "error": f"Unknown method '{method_id}'"
            + (f". Did you mean: {', '.join(matches)}?" if matches else "")
        }

    try:
        method, in_args, out_args = await asyncio.gather(
            plc.client.get_method(method_id),
            plc.client.get_method_inargs(method_id),
            plc.client.get_method_outargs(method_id),
        )
        return enrich_method_definition(method, in_args, out_args)
    except Exception as e:
        logger.error(f"[{plc_ip}] get_method({method_id}) failed: {e}")
        return {"error": str(e)}


@mcp.tool()
async def invoke_method(
    ctx: Context,
    plc_ip: str,
    method_id: str,
    arguments: dict | None = None,
    wait: bool = True,
) -> dict:
    """Invoke a method. Pass `arguments` as a flat dict {name: value}.

    wait=True (default): blocks until done/error. Returns {status, run_id, out_args}.
    wait=False: returns immediately with run_id; poll with get_method_run.
    Example: invoke_method(plc_ip, "0-0-ntpclient-updatetime")
    """
    plc, err = _require_plc(plc_ip)
    if err:
        return err
    if method_id not in plc.methods:
        matches = get_close_matches(method_id, plc.methods, n=3, cutoff=0.6)
        return {
            "error": f"Unknown method '{method_id}'"
            + (f". Did you mean: {', '.join(matches)}?" if matches else "")
        }

    if plc_ip in _READONLY_HOSTS:
        _audit_log("invoke_method", plc_ip, {"method": method_id, "args": arguments or {}}, "refused: read-only host")
        return {"error": f"PLC {plc_ip} is read-only (WAGO_READONLY_HOSTS / fleet.txt '# readonly'); method invocation refused."}

    # Gate 1: a dangerous method (reboot/reset/firmware) is never executed
    # autonomously. In GitOps mode it may be *proposed* for human PR approval;
    # in live mode it is denied unless explicitly allowlisted.
    dangerous = is_dangerous_method(method_id) and method_id not in _ALLOWED_METHODS

    if _GITOPS_MODE:
        from gitops import ops_fragment
        if dangerous:
            _audit_log("invoke_method.proposed", plc_ip,
                       {"method": method_id, "args": arguments or {}, "danger": True}, "proposed-critical")
        return ops_fragment(plc_ip, method_id, arguments, _AGENT_ID, dangerous=dangerous, repo=_GITOPS_REPO)

    if dangerous:
        _audit_log("invoke_method", plc_ip, {"method": method_id, "args": arguments or {}}, "denied: dangerous method")
        return {"error": (
            f"Method '{method_id}' is denied by safety policy (dangerous; not in WAGO_ALLOW_METHODS). "
            f"Use GitOps mode for a human-reviewed path, or add the exact method ID to WAGO_ALLOW_METHODS."
        )}

    try:
        run = await plc.client.invoke_method(method_id, arguments, sync=wait)
    except Exception as e:
        logger.error(f"[{plc_ip}] invoke_method({method_id}) failed: {e}")
        _audit_log("invoke_method", plc_ip, {"method": method_id, "args": arguments or {}}, f"error: {e}")
        return {"error": str(e)}

    attrs = run.get("attributes", {})
    status = attrs.get("executionStatus", "unknown")
    logger.info(f"[{plc_ip}] method {method_id} → {status}")
    _audit_log("invoke_method", plc_ip, {"method": method_id, "args": arguments or {}}, status)

    response: dict = {
        "status": status,
        "run_id": run.get("id"),
        "out_args": attrs.get("outArgs", {}),
    }
    if status == "error":
        response["error_detail"] = attrs.get("detail")
        response["error_code"] = attrs.get("code")
    return response


@mcp.tool()
async def get_method_run(
    ctx: Context, plc_ip: str, method_id: str, run_id: str
) -> dict:
    """Poll an async method run. Use after invoke_method(wait=False) to check status."""
    plc, err = _require_plc(plc_ip)
    if err:
        return err
    try:
        run = await plc.client.get_method_run(method_id, run_id)
    except Exception as e:
        return {"error": str(e)}
    attrs = run.get("attributes", {})
    return {
        "status": attrs.get("executionStatus"),
        "run_id": run.get("id"),
        "out_args": attrs.get("outArgs", {}),
        "timeout_remaining": attrs.get("timeout"),
        "error_detail": attrs.get("detail"),
    }


# ───────────────────────── Tools: watchlists (monitoring lists) ─────────────────────────

@mcp.tool()
async def create_watchlist(
    ctx: Context,
    plc_ip: str,
    parameter_ids: list[str],
    timeout_seconds: int = 60,
) -> dict:
    """Create a server-side watchlist of parameters for efficient repeated polling.

    Returns {watchlist_id, parameters: [{id, value, dataType}]} with initial values.
    Watchlist auto-expires after timeout_seconds of inactivity (reset on each read).
    Use timeout_seconds=0 for one-shot read.
    """
    plc, err = _require_plc(plc_ip)
    if err:
        return err

    unknown = [p for p in parameter_ids if p not in plc.parameters]
    if unknown:
        return {"error": f"Unknown parameter IDs: {unknown}"}

    try:
        body = await plc.client.create_monitoring_list(
            parameter_ids, timeout=timeout_seconds
        )
        parsed = parse_watchlist_response(body)
        logger.info(
            f"[{plc_ip}] created watchlist {parsed['id']} "
            f"with {len(parameter_ids)} param(s), timeout={timeout_seconds}s"
        )
        return {
            "watchlist_id": parsed["id"],
            "timeout": parsed["timeout"],
            "parameters": parsed["parameters"],
        }
    except Exception as e:
        logger.error(f"[{plc_ip}] create_watchlist failed: {e}")
        return {"error": str(e)}


@mcp.tool()
async def read_watchlist(ctx: Context, plc_ip: str, watchlist_id: str) -> dict:
    """Read current values from an existing watchlist. Resets the timeout."""
    plc, err = _require_plc(plc_ip)
    if err:
        return err
    try:
        body = await plc.client.get_monitoring_list(watchlist_id, include_parameters=True)
        parsed = parse_watchlist_response(body)
        return {
            "watchlist_id": parsed["id"],
            "timeout": parsed["timeout"],
            "parameters": parsed["parameters"],
        }
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def delete_watchlist(ctx: Context, plc_ip: str, watchlist_id: str) -> dict:
    """Delete a watchlist to free server resources before timeout."""
    plc, err = _require_plc(plc_ip)
    if err:
        return err
    try:
        await plc.client.delete_monitoring_list(watchlist_id)
        logger.info(f"[{plc_ip}] deleted watchlist {watchlist_id}")
        return {"status": "ok"}
    except Exception as e:
        return {"error": str(e)}


# ───────────────────────── Prompt for agents ─────────────────────────

@mcp.prompt()
def wago_assistant(query: str) -> list[base.Message]:
    instructions = [
        "You are an agent operating WAGO PLCs via the WDx REST API.",
        "",
        "**Audit:**",
        "- `get_plc_audit_log(plc_ip='', action='', limit=50)` — query the tamper-evident audit chain.",
        "",
        "**Standard workflow:**",
        "1. `list_plcs()` to see available PLCs, or read resource `wago://catalog`.",
        "2. `describe_plc(plc_ip)` for capability summary.",
        "3. `find_parameters(plc_ip, query, writeable_only=…)` to locate parameters by keyword.",
        "4. `get_parameter(plc_ip, id)` to read one (enum labels resolved automatically).",
        "5. `set_parameters(plc_ip, [{id, value}, …])` to write (validated upfront).",
        "",
        "**For methods:**",
        "1. `find_methods(plc_ip, query)` to discover.",
        "2. `get_method(plc_ip, id)` for the inArgs/outArgs schema in one call.",
        "3. `invoke_method(plc_ip, id, arguments={...}, wait=True)` to execute.",
        "",
        "**For repeated polling**: use watchlists.",
        "1. `create_watchlist(plc_ip, [param_ids], timeout_seconds=60)` once.",
        "2. `read_watchlist(plc_ip, watchlist_id)` repeatedly (resets timeout).",
        "3. `delete_watchlist(plc_ip, watchlist_id)` when done.",
        "",
        "**For fleet-wide reads (most efficient):**",
        "- `get_parameters_bulk(requests=[{plc_ip, parameter_id}, ...])` — reads one param from N PLCs in parallel.",
        "  Use this instead of looping get_parameter when querying the same parameter across multiple PLCs.",
        "",
        "**Error contract**: every tool returns `{'error': str}` on failure. On success, no `error` key.",
        "",
        "**GitOps mode** (when GITOPS_MODE=true on the server):",
        "- `set_parameters` and `invoke_method` return `{status: 'proposed', config_file, desired_state_yaml/ops_yaml, next_step}`.",
        f"- Do NOT call WDA directly. Instead: commit the returned YAML to {_GITOPS_REPO}/<config_file> and open a PR.",
        "- Use the GitHub MCP tool to create/update the file and open the PR.",
        "- For set_parameters: merge new keys into plcs/<ip>.yaml under `managed_parameters` (preserve existing keys).",
        "- For invoke_method: create ops/<id>.yaml with the returned ops_yaml (one-shot, deleted after CI applies it).",
        "",
        "**Safety gates (cannot be bypassed by an agent):**",
        "- Read-only PLCs (WAGO_READONLY_HOSTS / fleet '# readonly') refuse all writes/invokes in every mode.",
        "- Dangerous methods (reboot/restart/factoryreset/firmware/format) are NEVER run autonomously.",
        "  Live mode: denied unless allowlisted. GitOps mode: proposed with `requires_human: CRITICAL` —",
        "  a human must set `approved_by` in the ops file; do NOT fill it yourself.",
    ]
    return [base.SystemMessage("\n".join(instructions)), base.UserMessage(query)]


# ───────────────────────── Entry point ─────────────────────────

async def main() -> None:
    _seed_audit_hash(os.getenv("AUDIT_LOG_FILE", DEFAULT_AUDIT_LOG))

    plcs = parse_plcs_from_env()
    logger.info(f"Discovering {len(plcs)} PLC(s) in parallel…")

    ok, failed = await plc_manager.register_many(plcs)

    logger.info(f"Registration: {len(ok)}/{len(plcs)} ready")
    if failed:
        logger.info(f"Skipped: {', '.join(failed)}")

    host = os.getenv("HOST", "0.0.0.0")
    port = os.getenv("PORT", "6042")
    transport = os.getenv("TRANSPORT", "streamable-http").strip().lower()

    api_key, is_new_key = resolve_api_key()
    if is_new_key:
        print_key_banner(api_key)

    global _AGENT_ID
    _AGENT_ID = "key-" + api_key[:8]

    tls_cert = os.getenv("MCP_TLS_CERT") or None
    tls_key  = os.getenv("MCP_TLS_KEY")  or None
    tls_password = os.getenv("MCP_TLS_KEY_PASSWORD") or None
    tls_enabled = bool(tls_cert and tls_key)
    scheme = "https" if tls_enabled else "http"

    if transport == "stdio":
        logger.info("MCP server transport: stdio (uvx / Claude Desktop direct mode)")
        mcp.run(transport="stdio")
        return

    if transport == "sse":
        endpoint = f"{scheme}://{host}:{port}/sse"
        logger.info(f"MCP server listening on {endpoint} (SSE — legacy)")
        base_app = mcp.sse_app()
    else:
        endpoint = f"{scheme}://{host}:{port}/mcp"
        logger.info(f"MCP server listening on {endpoint} (Streamable HTTP)")
        base_app = mcp.streamable_http_app()

    if tls_enabled:
        logger.info(f"[tls] MCP endpoint TLS enabled (cert: {tls_cert})")
    else:
        logger.warning(
            "[tls] MCP endpoint TLS DISABLED — plain HTTP. "
            "Set MCP_TLS_CERT + MCP_TLS_KEY to enable. "
            "Also update wago_proxy.py and .mcp.json URLs to https:// when enabling."
        )

    app = AuthMiddleware(base_app, api_key)
    if not is_new_key:
        logger.info("[auth] Bearer auth enabled — GET /health is exempt")

    config = uvicorn.Config(
        app,
        host=host,
        port=int(port),
        log_level="warning",
        ssl_certfile=tls_cert,
        ssl_keyfile=tls_key,
        ssl_keyfile_password=tls_password,
    )
    server = uvicorn.Server(config)
    try:
        await server.serve()
    finally:
        await plc_manager.close_all()


def cli_main() -> None:
    """Entry point for PyPI / uvx installation."""
    asyncio.run(main())


if __name__ == "__main__":
    asyncio.run(main())
