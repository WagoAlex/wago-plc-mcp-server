#!/usr/bin/env python3
"""Reconcile a wago-plc-config YAML against a live PLC.

Usage:
  apply.py plcs/192.168.42.118.yaml            # diff only (dry-run)
  apply.py plcs/192.168.42.118.yaml --execute  # apply drift to PLC
  apply.py ops/abc12345.yaml --execute         # invoke method + delete file
"""
import argparse
import asyncio
import os
import subprocess
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def _client():
    from wda_client import WDAClient  # noqa: PLC0415 - local import after sys.path patch
    return WDAClient


def _audit(action: str, plc_ip: str, result: str, **details) -> None:
    """Record one action. Writes the hash chain when AUDIT_LOG_FILE is set, and
    forwards to AUDIT_SYSLOG when that is set.

    A CI runner usually has no persistent volume for the chain, so syslog alone
    is a valid configuration - and the one that matters there, since a record
    that only ever existed on an ephemeral runner is not an audit trail.
    """
    from audit import append_audit, build_entry, forward_to_syslog  # noqa: PLC0415 - after sys.path patch

    path = os.getenv("AUDIT_LOG_FILE", "").strip()
    try:
        if path:
            append_audit(path, action, plc_ip, "apply.py", result, **details)  # forwards internally
        elif os.getenv("AUDIT_SYSLOG", "").strip():
            from audit import GENESIS  # noqa: PLC0415

            line, _ = build_entry(action, plc_ip, "apply.py", result, GENESIS, details)
            forward_to_syslog(line)
    except Exception as e:  # never let logging failure abort a reconcile
        print(f"[audit] WARNING: could not write audit record: {e}", file=sys.stderr)


def _coerce(desired, current):
    """Cast desired value to the same type as the live PLC value before PATCH."""
    if isinstance(current, bool):
        return desired if isinstance(desired, bool) else str(desired).lower() == "true"
    if isinstance(current, (int, float)) and not isinstance(current, bool):
        try:
            return type(current)(desired)
        except (ValueError, TypeError):
            return desired
    return desired  # string / unknown - send as-is


async def apply_desired_state(data: dict, execute: bool) -> int:
    """Read current PLC state, diff against desired, apply only drift. Returns exit code."""
    from safety import compute_readonly_hosts  # noqa: PLC0415 - local import after sys.path patch

    WDAClient = _client()
    plc_ip = data["plc_ip"]
    desired: dict = data["managed_parameters"]

    if plc_ip in compute_readonly_hosts():
        print(f"[{plc_ip}] REFUSED: read-only host (WAGO_READONLY_HOSTS / fleet '# readonly').", file=sys.stderr)
        _audit("apply_desired_state", plc_ip, "refused: read-only host")
        return 1

    client = WDAClient(
        plc_ip,
        os.getenv("DEFAULT_PLC_USERNAME", "admin"),
        os.getenv("DEFAULT_PLC_PASSWORD", "wago"),
        timeout=float(os.getenv("WAGO_TIMEOUT_SECONDS", "45")),
    )
    try:
        current: dict[str, object] = {}
        for param_id in desired:
            attrs = await client.get_parameter(param_id)
            current[param_id] = attrs.get("value")

        drift = {
            k: (current.get(k), v)
            for k, v in desired.items()
            if str(current.get(k)).lower() != str(v).lower()  # bool False/"false" safe
        }

        if not drift:
            print(f"[{plc_ip}] In sync - nothing to apply.")
            return 0

        print(f"[{plc_ip}] Drift detected ({len(drift)} parameter(s)):")
        for k, (cur, want) in drift.items():
            print(f"  {k}: {cur!r} → {want!r}")

        if not execute:
            print("\nDry-run - pass --execute to apply.")
            return 0

        patches = [{"id": k, "value": _coerce(v, current.get(k))} for k, (_, v) in drift.items()]
        await client.set_parameters(patches)
        print(f"[{plc_ip}] Applied {len(patches)} change(s).")
        _audit("apply_desired_state", plc_ip, "ok", changed=[p["id"] for p in patches])
        return 0
    except Exception as e:
        print(f"[{plc_ip}] ERROR: {e}", file=sys.stderr)
        return 1
    finally:
        await client.close()


async def apply_ops(data: dict, path: Path, execute: bool) -> int:
    """Invoke a one-shot method and delete the ops file on success. Returns exit code."""
    from safety import compute_readonly_hosts, is_dangerous_method  # noqa: PLC0415 - local import after sys.path patch

    WDAClient = _client()
    plc_ip = data["plc_ip"]
    method_id = data["method_id"]
    arguments = data.get("arguments") or {}
    # approved_by: a human sets it during PR review. WAGO_APPROVED_BY lets the CI
    # pipeline inject the merging reviewer's identity so it can't be forged in the
    # agent-authored YAML. Either source counts; both empty = refused.
    approved_by = os.getenv("WAGO_APPROVED_BY", "").strip() or str(data.get("approved_by", "")).strip()

    if plc_ip in compute_readonly_hosts():
        print(f"[{plc_ip}] REFUSED: read-only host (WAGO_READONLY_HOSTS / fleet '# readonly').", file=sys.stderr)
        _audit("apply_ops", plc_ip, "refused: read-only host", method=method_id)
        return 1

    # Gate 3: a dangerous op must carry a human-set approved_by (filled during PR
    # review). The agent's proposal never fills it, so an unreviewed reboot is refused.
    if is_dangerous_method(method_id) and not approved_by:
        print(
            f"[{plc_ip}] REFUSED: '{method_id}' is a dangerous method with no `approved_by`. "
            f"A human must set approved_by in the ops file before this can run.",
            file=sys.stderr,
        )
        _audit("apply_ops", plc_ip, "refused: dangerous, no approved_by", method=method_id)
        return 1

    print(f"[{plc_ip}] invoke_method: {method_id}  args={arguments}")

    if not execute:
        print("Dry-run - pass --execute to apply.")
        return 0

    client = WDAClient(
        plc_ip,
        os.getenv("DEFAULT_PLC_USERNAME", "admin"),
        os.getenv("DEFAULT_PLC_PASSWORD", "wago"),
        timeout=float(os.getenv("WAGO_TIMEOUT_SECONDS", "45")),
    )
    try:
        result = await client.invoke_method(method_id, arguments, sync=True)
        print(f"[{plc_ip}] {result}")
        _audit("apply_ops", plc_ip, "ok", method=method_id, args=arguments, approved_by=approved_by)
        path.unlink()
        print(f"Deleted {path}")
        return 0
    except Exception as e:
        print(f"[{plc_ip}] ERROR: {e}", file=sys.stderr)
        return 1
    finally:
        await client.close()


# Where the flash tool lives. Overridable with FWUPDATE_TOOL for deployments
# that keep it outside this checkout.
FWUPDATE_TOOL = Path(__file__).resolve().parent.parent / "fwupdate" / "fw_update.py"


def apply_firmware(data: dict, path: Path, execute: bool) -> int:
    """Run a one-shot firmware update, then delete the ops file - the same
    lifecycle as a reboot op.

    The flash itself is delegated to fwupdate/fw_update.py rather than
    reimplemented here: it owns the WDA upload protocol, the reboot poll and
    the Finish-on-Unconfirmed timing. This function's job is the gate.

    The ops file IS the authorization, and fw_update.py re-verifies that it is
    committed and signed off - deliberately not trusting the dict we parsed
    here, since a runner could be handed a modified working tree.
    """
    from safety import compute_readonly_hosts  # noqa: PLC0415 - local import after sys.path patch

    plc_ip = data["plc_ip"]
    target_version = str(data.get("target_version", "")).strip()
    approved_by = os.getenv("WAGO_APPROVED_BY", "").strip() or str(data.get("approved_by", "")).strip()

    if plc_ip in compute_readonly_hosts():
        print(f"[{plc_ip}] REFUSED: read-only host (WAGO_READONLY_HOSTS / fleet '# readonly').", file=sys.stderr)
        _audit("apply_firmware", plc_ip, "refused: read-only host", target_version=target_version)
        return 1

    if not target_version:
        print(f"[{plc_ip}] REFUSED: ops file has no `target_version`.", file=sys.stderr)
        _audit("apply_firmware", plc_ip, "refused: no target_version")
        return 1

    # Firmware is always dangerous - there is no non-dangerous variant to check for.
    if not approved_by:
        print(
            f"[{plc_ip}] REFUSED: firmware update with no `approved_by`. "
            f"A human must set approved_by in the ops file before this can run.",
            file=sys.stderr,
        )
        _audit("apply_firmware", plc_ip, "refused: no approved_by", target_version=target_version)
        return 1

    reflash = " [re-flash: same version]" if data.get("allow_reflash") else ""
    print(f"[{plc_ip}] firmware_update -> {target_version}{reflash}  (approved_by: {approved_by})")

    if not execute:
        # Deliberately does NOT contact the device or upload ~200 MB during a PR
        # check. The gate is what a reviewer needs to see; the flash happens on merge.
        print("Dry-run - pass --execute to apply.")
        return 0

    fw_update = Path(os.getenv("FWUPDATE_TOOL", "") or FWUPDATE_TOOL)
    if not fw_update.is_file():
        print(f"[{plc_ip}] ERROR: {fw_update} not found", file=sys.stderr)
        _audit("apply_firmware", plc_ip, "error: fwupdate tool missing", target_version=target_version)
        return 1

    # allow_reflash is declared in the REVIEWED yaml, not injected by CI: writing
    # the version a device already runs is a decision a reviewer should see.
    env = {
        **os.environ,
        "PLC_IP": plc_ip,
        "PLC_USERNAME": os.getenv("DEFAULT_PLC_USERNAME", "admin"),
        "PLC_PASSWORD": os.getenv("DEFAULT_PLC_PASSWORD", ""),
        "FW_OPS_FILE": str(path.resolve()),
        "TARGET_VERSION": target_version,
        "WAGO_APPROVED_BY": approved_by,
        "FW_ALLOW_REFLASH": "true" if data.get("allow_reflash") else "false",
    }
    rc = subprocess.run([sys.executable, str(fw_update)], env=env).returncode
    if rc != 0:
        print(f"[{plc_ip}] firmware update FAILED (exit {rc}) - ops file kept for retry", file=sys.stderr)
        return rc

    # fw_update.py already wrote its own detailed audit records; this one closes
    # the ops lifecycle so the trail matches a reboot's.
    _audit("apply_firmware", plc_ip, "ok", target_version=target_version, approved_by=approved_by)
    path.unlink()
    print(f"Deleted {path}")
    return 0


async def run(proposal_path: Path, execute: bool) -> int:
    data = yaml.safe_load(proposal_path.read_text())
    if "managed_parameters" in data:
        return await apply_desired_state(data, execute)
    if data.get("action") == "invoke_method":
        return await apply_ops(data, proposal_path, execute)
    if data.get("action") == "firmware_update":
        return apply_firmware(data, proposal_path, execute)
    print(f"Unknown YAML shape in {proposal_path}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("proposal", help="Path to a plcs/<ip>.yaml or ops/<id>.yaml file")
    ap.add_argument("--execute", action="store_true", help="Apply changes (default: dry-run)")
    args = ap.parse_args()

    path = Path(args.proposal)
    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        sys.exit(1)

    sys.exit(asyncio.run(run(path, args.execute)))
