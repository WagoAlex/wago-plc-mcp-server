"""Guardrails against autonomous dangerous actions on production PLCs.

Three independent gates (see docs/gitops/README.md "Safety model"):
  1. Dangerous-method denylist — block reboot/reset/firmware unless allowlisted.
  2. Per-PLC read-only         — freeze production PLCs in every mode.
  3. apply.py human-gate       — require approved_by + audit log on apply.

None of these depend on the agent behaving. They are enforced at the tool
boundary (src/main.py) and the reconciler (scripts/apply.py).
"""

import os
import re
from pathlib import Path

# Dangerous-action roots, matched case-insensitively against the hyphen/dot/
# underscore-split segments of a method ID (segment startswith root). Segment
# matching — not raw substring — handles WDA's hyphenated IDs ("firmware-update")
# and avoids false hits like "information" containing "format".
# ponytail: tight on purpose — bare "reset" would catch benign params. Widen this
# tuple, or grant a specific method via WAGO_ALLOW_METHODS.
DANGEROUS_METHOD_ROOTS = (
    "reboot",
    "restart",
    "factory",   # factory-reset, factoryreset, factory-default
    "firmware",  # firmware-update, firmwareupdate
    "format",    # sdcard-format, etc.
)

_SPLIT = re.compile(r"[^a-z0-9]+")


def is_dangerous_method(method_id: str) -> bool:
    """True if any segment of the method ID starts with a dangerous-action root.

    Non-ASCII is folded out first so zero-width/homoglyph tricks (e.g. "re\\u200bboot")
    can't split a dangerous word into harmless segments.
    """
    if not method_id:
        return False
    ascii_id = method_id.encode("ascii", "ignore").decode().lower()
    segments = _SPLIT.split(ascii_id)
    return any(seg.startswith(root) for seg in segments for root in DANGEROUS_METHOD_ROOTS)


def _parse_csv_set(raw: str | None) -> frozenset[str]:
    return frozenset(item.strip() for item in (raw or "").split(",") if item.strip())


def parse_allowed_methods(raw: str | None) -> frozenset[str]:
    """Exact method IDs explicitly re-enabled despite matching the denylist.

    Source: WAGO_ALLOW_METHODS env (CSV). Only the live (non-GitOps) server path
    consults this — the GitOps path is gated by human PR review instead.
    """
    return _parse_csv_set(raw)


def parse_readonly_hosts(raw: str | None) -> frozenset[str]:
    """PLC IPs that reject all writes/invokes regardless of mode (WAGO_READONLY_HOSTS, CSV)."""
    return _parse_csv_set(raw)


def compute_readonly_hosts() -> frozenset[str]:
    """Effective read-only host set: WAGO_READONLY_HOSTS env + fleet-file `# readonly` tags.

    Shared by the MCP server (main.py) and the reconciler (apply.py) so a frozen PLC
    is frozen on both paths. An unreadable fleet file degrades to the env set, never aborts.
    """
    hosts = set(parse_readonly_hosts(os.getenv("WAGO_READONLY_HOSTS")))
    hosts_file = os.getenv("WAGO_PLC_HOSTS_FILE", "").strip()
    if hosts_file:
        try:
            for line in Path(hosts_file).read_text().splitlines():
                ip, _, comment = line.partition("#")
                ip = ip.strip()
                if ip and "readonly" in comment.lower():
                    hosts.add(ip)
        except OSError:
            pass  # fleet file missing/unreadable — env set still applies
    return frozenset(hosts)
