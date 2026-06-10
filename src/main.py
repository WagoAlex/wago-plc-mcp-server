"""WAGO PLC MCP Server — optimized for OpenClaw agents (small local models).

12 tools, compact responses, smart pre-validation.
"""
import asyncio
import os
import re
from difflib import get_close_matches

from dotenv import load_dotenv
from loguru import logger
from mcp.server.fastmcp import FastMCP, Context
from mcp.server.fastmcp.prompts import base

from logging_config import setup_logging
from plc_manager import PLCManager
from enricher import enrich_parameter, enrich_method_definition, parse_watchlist_response

# ───────────────────────── Bootstrap ─────────────────────────

load_dotenv()
setup_logging(
    log_file=os.getenv("LOG_FILE", "/app/mcp_server.log"),
    level=os.getenv("LOG_LEVEL", "INFO"),
)

plc_manager = PLCManager(
    timeout_seconds=float(os.getenv("WAGO_TIMEOUT_SECONDS", "10")),
    page_limit=int(os.getenv("WAGO_PAGE_LIMIT", "500")),
    max_concurrent_registrations=int(os.getenv("WAGO_MAX_CONCURRENT_REGISTRATIONS", "5")),
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

FIND_LIMIT_MAX = 100
FIND_LIMIT_DEFAULT = 20


# ───────────────────────── Helpers ─────────────────────────

def _parse_plcs_from_env() -> list[tuple[str, str, str]]:
    """Parse PLC list from environment, supporting three formats.

    1. WAGO_PLC_HOSTS (preferred for shared credentials):
         WAGO_PLC_HOSTS=10.0.0.1,10.0.0.2,10.0.0.3
         DEFAULT_PLC_USERNAME=admin
         DEFAULT_PLC_PASSWORD=secret

    2. PLC_PASSWORDS_<ip-with-underscores> (per-PLC credentials, backward-compat):
         PLC_PASSWORDS_10_0_0_1=secret_a
         PLC_PASSWORDS_10_0_0_2=secret_b

    3. Both formats can be combined; PLC_PASSWORDS_* overrides WAGO_PLC_HOSTS for
       matching IPs.
    """
    user = os.getenv("DEFAULT_PLC_USERNAME", "admin")
    default_pwd = os.getenv("DEFAULT_PLC_PASSWORD", "wago")
    plcs: dict[str, tuple[str, str]] = {}  # ip → (user, pwd)

    # Format 1: comma-separated list
    hosts_csv = os.getenv("WAGO_PLC_HOSTS", "").strip()
    if hosts_csv:
        for ip in (h.strip() for h in hosts_csv.split(",")):
            if ip:
                plcs[ip] = (user, default_pwd)

    # Format 2: per-IP env vars (override or extend)
    for key, val in os.environ.items():
        m = re.match(r"^PLC_PASSWORDS_(\d+_\d+_\d+_\d+)$", key)
        if m:
            ip = m.group(1).replace("_", ".")
            plcs[ip] = (user, val or default_pwd)

    return [(ip, u, p) for ip, (u, p) in plcs.items()]


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
async def describe_plc(ctx: Context, plc_ip: str) -> dict:
    """Get capability summary for a PLC: counts + feature names. Cheap, cached."""
    plc, err = _require_plc(plc_ip)
    if err:
        return err
    return {
        "ip": plc_ip,
        "parameter_count": len(plc.parameters),
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
    """Search parameter IDs by substring/fuzzy match. Returns up to `limit` matches (default 20, max 100).

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

    Example — read firmware version from all PLCs:
    [{"plc_ip": "192.168.42.110", "parameter_id": "0-0-version-firmwareversion"}, ...]
    """
    async def _fetch(req: dict) -> dict:
        ip = req.get("plc_ip", "")
        pid = req.get("parameter_id", "")
        plc, err = _require_plc(ip)
        if err:
            return {"plc_ip": ip, "parameter_id": pid, "error": err["error"]}
        if pid not in plc.parameters:
            return {"plc_ip": ip, "parameter_id": pid, "error": f"Unknown parameter '{pid}'"}
        try:
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

    unknown = [p.get("id") for p in parameters if p.get("id") not in plc.parameters]
    if unknown:
        return {"error": f"Unknown parameter IDs: {unknown}"}

    read_only = [p["id"] for p in parameters if p["id"] not in plc.param_writeable]
    if read_only:
        return {"error": f"Read-only parameter IDs (cannot be set): {read_only}"}

    try:
        result = await plc.client.set_parameters(parameters)
        logger.info(f"[{plc_ip}] set {len(parameters)} parameter(s)")
        return {"status": "ok", "result": result}
    except Exception as e:
        logger.error(f"[{plc_ip}] set_parameters failed: {e}")
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
        return {"error": f"Unknown method '{method_id}'"}

    try:
        run = await plc.client.invoke_method(method_id, arguments, sync=wait)
    except Exception as e:
        logger.error(f"[{plc_ip}] invoke_method({method_id}) failed: {e}")
        return {"error": str(e)}

    attrs = run.get("attributes", {})
    status = attrs.get("executionStatus", "unknown")
    logger.info(f"[{plc_ip}] method {method_id} → {status}")

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
    ]
    return [base.SystemMessage("\n".join(instructions)), base.UserMessage(query)]


# ───────────────────────── Entry point ─────────────────────────

async def main() -> None:
    plcs = _parse_plcs_from_env()
    logger.info(f"Discovering {len(plcs)} PLC(s) in parallel…")

    ok, failed = await plc_manager.register_many(plcs)

    logger.info(f"Registration: {len(ok)}/{len(plcs)} ready")
    if failed:
        logger.info(f"Skipped: {', '.join(failed)}")

    host = os.getenv("HOST", "0.0.0.0")
    port = os.getenv("PORT", "6042")
    transport = os.getenv("TRANSPORT", "streamable-http").strip().lower()

    if transport == "sse":
        endpoint = f"http://{host}:{port}/sse"
        logger.info(f"MCP server listening on {endpoint} (SSE — legacy)")
        run_fn = mcp.run_sse_async
    else:
        endpoint = f"http://{host}:{port}/mcp"
        logger.info(f"MCP server listening on {endpoint} (Streamable HTTP)")
        run_fn = mcp.run_streamable_http_async

    try:
        await run_fn()
    finally:
        await plc_manager.close_all()


if __name__ == "__main__":
    asyncio.run(main())
