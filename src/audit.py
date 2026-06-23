"""Tamper-evident audit chain — single source of the entry format + hashing.

Shared by the MCP server (src/main.py, keeps the prev hash in memory) and the
GitOps reconciler (scripts/apply.py, reads the prev hash from the log tail each
run). One implementation of the JSON-line format so both writers stay compatible
with the AUDIT loguru sink (which emits raw ``{message}\\n``).
"""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

GENESIS = "0" * 64


def build_entry(
    action: str, plc_ip: str, agent: str, result: str, prev_hash: str, details: dict
) -> tuple[str, str]:
    """Return (json_line, new_hash) for one audit record chained off prev_hash."""
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "plc": plc_ip,
        "agent": agent,
        "result": result,
        "prev": prev_hash,
        **details,
    }
    line = json.dumps(entry, default=str)
    return line, hashlib.sha256(line.encode()).hexdigest()


def read_prev_hash(audit_log_path: str) -> str:
    """Hash of the last audit line, or GENESIS if the file is missing/empty/corrupt.

    Reads only the tail (4 KB) — safe on large logs.
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

    ponytail: not concurrency-safe across two live writers — apply.py runs in CI,
    separate from the server, so its records chain off whatever tail it sees. The
    PR + CI run log is the authoritative human-gate record; this is the second copy.
    """
    prev = read_prev_hash(audit_log_path)
    line, _ = build_entry(action, plc_ip, agent, result, prev, details)
    with Path(audit_log_path).open("a") as f:
        f.write(line + "\n")
    return line
