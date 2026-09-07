"""Tamper-evident audit chain - single source of the entry format + hashing.

Shared by the MCP server (src/main.py, keeps the prev hash in memory) and the
GitOps reconciler (scripts/apply.py, reads the prev hash from the log tail each
run). One implementation of the JSON-line format so both writers stay compatible
with the AUDIT loguru sink (which emits raw ``{message}\\n``).
"""
import hashlib
import json
import logging
import logging.handlers
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

GENESIS = "0" * 64

# Parameter IDs / argument names whose VALUES must never land in the audit log
# (the log is readable by every authenticated agent via get_plc_audit_log).
# IDs stay visible - the trail still shows WHAT changed, just not the secret.
_SENSITIVE = re.compile(
    r"password|passwd|secret|token|credential|communit|api-?key|private-?key|passphrase",
    re.IGNORECASE,
)
REDACTED = "<redacted>"


def redact_details(obj):
    """Recursively replace values of sensitive keys/parameter-IDs with REDACTED.

    Handles both shapes the writers produce:
      {"params": [{"id": "...-community...", "value": SECRET}, ...]}   (set_parameters)
      {"args": {"password": SECRET, ...}}                              (invoke_method)
    Returns a new structure - never mutates the input.
    """
    if isinstance(obj, dict):
        # WDA parameter shape: sensitive name lives in the "id" VALUE
        if "id" in obj and "value" in obj and _SENSITIVE.search(str(obj["id"])):
            return {**obj, "value": REDACTED}
        return {
            k: (REDACTED if _SENSITIVE.search(str(k)) and not isinstance(v, (dict, list)) else redact_details(v))
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [redact_details(item) for item in obj]
    return obj

# Volume-backed default - /app/data is the ./data bind mount, so the tamper-
# evident chain survives `docker rm -f wmcp`. Never default to /app/audit.log
# (container layer, lost on removal).
DEFAULT_AUDIT_LOG = "/app/data/audit.log"


def build_entry(
    action: str, plc_ip: str, agent: str, result: str, prev_hash: str, details: dict
) -> tuple[str, str]:
    """Return (json_line, new_hash) for one audit record chained off prev_hash.

    Sensitive values in details are redacted BEFORE hashing, so the chain
    stays verifiable over exactly what is stored.
    """
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "plc": plc_ip,
        "agent": agent,
        "result": result,
        "prev": prev_hash,
        **redact_details(details),
    }
    line = json.dumps(entry, default=str)
    return line, hashlib.sha256(line.encode()).hexdigest()


# --- external syslog ---------------------------------------------------------
# An on-disk chain proves nothing to an auditor if the host that writes it is
# also the host that could rewrite it. Forwarding every record to a syslog
# collector the operator does not control from here is the standard answer, and
# it is the copy that survives the container being removed.
#
#   AUDIT_SYSLOG=udp://10.0.0.5:514   (tcp:// for a lossless collector)
#
# Best-effort by design: a collector that is down must never block or fail a
# PLC write, so send errors are swallowed after one warning.
_SYSLOG_HANDLER: logging.Handler | None = None
_SYSLOG_FAILED = False


def _syslog_handler() -> logging.Handler | None:
    """Build the handler once from AUDIT_SYSLOG, or None when unconfigured."""
    global _SYSLOG_HANDLER, _SYSLOG_FAILED
    if _SYSLOG_HANDLER is not None or _SYSLOG_FAILED:
        return _SYSLOG_HANDLER

    target = os.getenv("AUDIT_SYSLOG", "").strip()
    if not target:
        _SYSLOG_FAILED = True
        return None
    try:
        url = urlparse(target if "://" in target else f"udp://{target}")
        socktype = __import__("socket").SOCK_STREAM if url.scheme == "tcp" else __import__("socket").SOCK_DGRAM
        handler = logging.handlers.SysLogHandler(
            address=(url.hostname, url.port or 514),
            facility=logging.handlers.SysLogHandler.LOG_LOCAL0,
            socktype=socktype,
        )
        handler.ident = "wago-plc-audit: "
        # Python appends a NUL by default; RFC 5424 has no such terminator and
        # strict collectors log it as a malformed trailing byte.
        handler.append_nul = False
        _SYSLOG_HANDLER = handler
        return handler
    except Exception as e:
        print(f"[audit] WARNING: syslog target {target!r} unusable: {e} - continuing without it")
        _SYSLOG_FAILED = True
        return None


def forward_to_syslog(line: str) -> None:
    """Emit one audit line to the configured collector. Never raises."""
    handler = _syslog_handler()
    if handler is None:
        return
    try:
        handler.emit(
            logging.LogRecord("wago-plc-audit", logging.INFO, __file__, 0, line, None, None)
        )
    except Exception:
        pass  # a collector outage must never break or delay a PLC operation


def read_prev_hash(audit_log_path: str) -> str:
    """Hash of the last audit line, or GENESIS if the file is missing/empty/corrupt.

    Reads only the tail (4 KB) - safe on large logs.
    """
    try:
        path = Path(audit_log_path)
        if not path.exists():
            return GENESIS
        with path.open("rb") as f:
            f.seek(0, 2)
            tail_size = min(f.tell(), 4096)
            f.seek(-tail_size, 2)
            tail = f.read().decode("utf-8", errors="replace")
        lines = [ln.strip() for ln in tail.splitlines() if ln.strip()]
        if not lines:
            return GENESIS
        last = lines[-1]
        json.loads(last)  # reject a partial write at a rotation boundary
        return hashlib.sha256(last.encode()).hexdigest()
    except Exception:
        return GENESIS


def append_audit(
    audit_log_path: str, action: str, plc_ip: str, agent: str, result: str, **details
) -> str:
    """One-shot append for external processes (apply.py). Chains from the file tail.

    ponytail: not concurrency-safe across two live writers - apply.py runs in CI,
    separate from the server, so its records chain off whatever tail it sees. The
    PR + CI run log is the authoritative human-gate record; this is the second copy.
    """
    prev = read_prev_hash(audit_log_path)
    line, _ = build_entry(action, plc_ip, agent, result, prev, details)
    with Path(audit_log_path).open("a") as f:
        f.write(line + "\n")
    forward_to_syslog(line)
    return line
