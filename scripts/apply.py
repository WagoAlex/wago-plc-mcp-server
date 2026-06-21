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
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def _client():
    from wda_client import WDAClient  # noqa: PLC0415 — local import after sys.path patch
    return WDAClient


def _coerce(desired, current):
    """Cast desired value to the same type as the live PLC value before PATCH."""
    if isinstance(current, bool):
        return desired if isinstance(desired, bool) else str(desired).lower() == "true"
    if isinstance(current, (int, float)) and not isinstance(current, bool):
        try:
            return type(current)(desired)
        except (ValueError, TypeError):
            return desired
    return desired  # string / unknown — send as-is


async def apply_desired_state(data: dict, execute: bool) -> int:
    """Read current PLC state, diff against desired, apply only drift. Returns exit code."""
    WDAClient = _client()
    plc_ip = data["plc_ip"]
    desired: dict = data["managed_parameters"]

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
            print(f"[{plc_ip}] In sync — nothing to apply.")
            return 0

        print(f"[{plc_ip}] Drift detected ({len(drift)} parameter(s)):")
        for k, (cur, want) in drift.items():
            print(f"  {k}: {cur!r} → {want!r}")

        if not execute:
            print("\nDry-run — pass --execute to apply.")
            return 0

        patches = [{"id": k, "value": _coerce(v, current.get(k))} for k, (_, v) in drift.items()]
        await client.set_parameters(patches)
        print(f"[{plc_ip}] Applied {len(patches)} change(s).")
        return 0
    except Exception as e:
        print(f"[{plc_ip}] ERROR: {e}", file=sys.stderr)
        return 1
    finally:
        await client.close()


async def apply_ops(data: dict, path: Path, execute: bool) -> int:
    """Invoke a one-shot method and delete the ops file on success. Returns exit code."""
    WDAClient = _client()
    plc_ip = data["plc_ip"]
    method_id = data["method_id"]
    arguments = data.get("arguments") or {}

    print(f"[{plc_ip}] invoke_method: {method_id}  args={arguments}")

    if not execute:
        print("Dry-run — pass --execute to apply.")
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
        path.unlink()
        print(f"Deleted {path}")
        return 0
    except Exception as e:
        print(f"[{plc_ip}] ERROR: {e}", file=sys.stderr)
        return 1
    finally:
        await client.close()


async def run(proposal_path: Path, execute: bool) -> int:
    data = yaml.safe_load(proposal_path.read_text())
    if "managed_parameters" in data:
        return await apply_desired_state(data, execute)
    if data.get("action") == "invoke_method":
        return await apply_ops(data, proposal_path, execute)
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
