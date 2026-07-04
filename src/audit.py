"""Tamper-evident audit chain — single source of the entry format + hashing.

Shared by the MCP server (src/main.py, keeps the prev hash in memory) and the
GitOps reconciler (scripts/apply.py, reads the prev hash from the log tail each
run). One implementation of the JSON-line format so both writers stay compatible
with the AUDIT loguru sink (which emits raw ``{message}\\n``).
"""
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

GENESIS = "0" * 64

# Parameter IDs / argument names whose VALUES must never land in the audit log
# (the log is readable by every authenticated agent via get_plc_audit_log).
# IDs stay visible — the trail still shows WHAT changed, just not the secret.
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
    Returns a new structure — never mutates the input.
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

# Volume-backed default — /app/data is the ./data bind mount, so the tamper-
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
