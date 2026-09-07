#!/usr/bin/env python3
"""
Update every device the git-committed firmware policy approves - sequentially,
one child process per device.

Sequential on purpose: firmware updates hit device-specific quirks (the
/tmp/fwupdate permission requirement, the Finish-on-Unconfirmed timing) that
are far easier to diagnose one at a time, and a batch of simultaneous reboots
multiplies the blast radius of any single undiscovered issue. One process per
device also means a crash mid-run cannot poison the next device.

    FW_POLICY_FILE=/policy/firmware-policy.yaml DRY_RUN=true python fleet.py

Per-device passwords follow the same convention as the MCP server: a Docker
secret at /run/secrets/plc_password_<ip_with_underscores>, falling back to
PLC_PASSWORD for the whole fleet.
"""
import os
import subprocess
import sys
from pathlib import Path

import authz

POLICY_FILE = os.environ.get("FW_POLICY_FILE", "/policy/firmware-policy.yaml")


def password_for(ip: str) -> str:
    secret = Path(f"/run/secrets/plc_password_{ip.replace('.', '_')}")
    if secret.is_file():
        return secret.read_text().strip()
    return os.environ.get("PLC_PASSWORD", "")


def main():
    try:
        policy, commit = authz.load_policy(POLICY_FILE)
    except authz.NotAuthorized as e:
        print(f"FATAL: refused - {e}", flush=True)
        return 1

    hosts = authz.approved_hosts(policy)
    dry = os.environ.get("DRY_RUN", "false").lower() in ("1", "true", "yes")
    print(f"==> Fleet update from {POLICY_FILE} @ {commit[:12]}", flush=True)
    print(f"    {len(hosts)} approved device(s){'  [DRY_RUN]' if dry else ''}", flush=True)
    for ip, rev in sorted(hosts.items()):
        print(f"    {ip} -> {rev}", flush=True)

    results = {}
    for ip, rev in sorted(hosts.items()):
        print(f"\n{'=' * 70}\n=== {ip} -> {rev}\n{'=' * 70}", flush=True)
        # The committed approval is also the disambiguator: passing it as
        # TARGET_VERSION is what lets a device whose order number matches
        # several bundles (PFC-G2 standard 4.9.1 vs red-autoupdate 4.9.50)
        # resolve at all - the git policy decides, not "latest wins".
        env = {**os.environ, "PLC_IP": ip, "PLC_PASSWORD": password_for(ip), "TARGET_VERSION": rev}
        rc = subprocess.run([sys.executable, str(Path(__file__).parent / "fw_update.py")], env=env).returncode
        results[ip] = rc
        if rc != 0:
            print(f"=== {ip}: FAILED (exit {rc}) - continuing with the rest of the fleet", flush=True)

    print(f"\n{'=' * 70}\n=== Fleet summary", flush=True)
    for ip, rc in sorted(results.items()):
        print(f"    {ip}: {'ok' if rc == 0 else f'FAILED (exit {rc})'}", flush=True)
    failed = [ip for ip, rc in results.items() if rc != 0]
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
