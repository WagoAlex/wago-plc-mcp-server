#!/usr/bin/env python3
"""
Deliver a WAGO .wup firmware image to a device via the WDA REST API and drive
the update to completion, printing live status/progress to stdout.

Verified live against a WP400 and a PFC200 G2 (both FW31, WDA 1.5.2).
See ../docs/wda-firmware-update.md for the full write-up of why each step
exists (Activate must precede Start, /tmp/fwupdate permission requirement,
the .raucb-not-.wup payload, the ~4MB chunk ceiling).

Env vars:
    PLC_IP          required
    PLC_USERNAME    default "admin"
    PLC_PASSWORD    required
    WUP_PATH        default "/firmware/update.wup" - path *inside the container*;
                     map the real file there via the compose volume mount
                     (see WUP_FILE_PATH in docker-compose.yml, a host path).
    CHUNK_SIZE      default 4000000 (~4MB, the verified safe ceiling)
    POLL_INTERVAL   default 6 (seconds between status polls)
    POLL_TIMEOUT    default 900 (seconds to wait for progress=100 before giving up)
"""
import json
import os
import sys
import time
import zipfile
from pathlib import Path

import httpx

STATUS_NAMES = {
    0: "Inactive",
    1: "Init",
    2: "Prepared",
    3: "Started",
    4: "Unconfirmed",
    5: "Confirmed",
    6: "Revert",
    7: "Error",
    8: "Finished",
    9: "NotAvailable",
}


def env(name, default=None, required=False):
    val = os.environ.get(name, default)
    if required and not val:
        print(f"FATAL: required env var {name} is not set", file=sys.stderr)
        sys.exit(1)
    return val


PLC_IP = env("PLC_IP", required=True)
USERNAME = env("PLC_USERNAME", "admin")
PASSWORD = env("PLC_PASSWORD", required=True)
WUP_PATH = env("WUP_PATH", "/firmware/update.wup")
CHUNK_SIZE = int(env("CHUNK_SIZE", "4000000"))
POLL_INTERVAL = int(env("POLL_INTERVAL", "6"))
POLL_TIMEOUT = int(env("POLL_TIMEOUT", "900"))
DRY_RUN = env("DRY_RUN", "false").lower() in ("1", "true", "yes")
BOUNDARY = "wdafwupdateboundary"

BASE = f"https://{PLC_IP}"


def show(msg):
    print(msg, flush=True)


def client():
    return httpx.Client(auth=(USERNAME, PASSWORD), verify=False, timeout=30.0)


def run_method(c, method_id, in_args=None):
    body = {
        "data": {
            "type": "runs",
            "attributes": {"inArgs": in_args or {}},
        }
    }
    r = c.post(
        f"{BASE}/wda/methods/{method_id}/runs",
        params={"result-behavior": "sync"},
        headers={"Content-Type": "application/vnd.api+json"},
        json=body,
    )
    return r.json()


def method_ok(resp):
    return resp.get("data", {}).get("attributes", {}).get("executionStatus") == "done"


def get_log_tail(c, count=10):
    resp = run_method(c, "0-0-firmwareupdate-getlastlogentries", {"EntryCount": {"value": count}})
    try:
        return resp["data"]["attributes"]["outArgs"]["Entries"]["value"]
    except (KeyError, TypeError):
        return []


def get_status(c):
    r = c.get(f"{BASE}/wda/parameters/0-0-firmwareupdate-status")
    val = r.json()["data"]["attributes"]["value"]
    return val, STATUS_NAMES.get(val, f"Unknown({val})")


def get_progress(c):
    r = c.get(f"{BASE}/wda/parameters/0-0-firmwareupdate-progress")
    return r.json()["data"]["attributes"]["value"]


def extract_raucb(wup_path):
    workdir = Path("/tmp/fwupdate_work")
    workdir.mkdir(exist_ok=True)
    with zipfile.ZipFile(wup_path) as zf:
        zf.extractall(workdir)
    raucb_files = list(workdir.glob("*.raucb"))
    if not raucb_files:
        show(f"FATAL: no .raucb bundle found inside {wup_path}")
        sys.exit(1)
    return raucb_files[0]


def upload_chunks(c, file_id, raucb_path):
    total = raucb_path.stat().st_size
    total_chunks = (total + CHUNK_SIZE - 1) // CHUNK_SIZE
    show(f"==> Uploading {total} bytes in {total_chunks} chunks of ~{CHUNK_SIZE} bytes")
    with open(raucb_path, "rb") as f:
        offset = 0
        chunk_num = 0
        while offset < total:
            data = f.read(CHUNK_SIZE)
            if not data:
                break
            end = offset + len(data) - 1
            chunk_num += 1

            body = (
                f"--{BOUNDARY}\r\n"
                f"Content-Type: application/octet-stream\r\n"
                f"Content-Range: bytes {offset}-{end}/{total}\r\n"
                f"\r\n"
            ).encode() + data + f"\r\n--{BOUNDARY}--\r\n".encode()

            r = c.patch(
                f"{BASE}/files/{file_id}",
                content=body,
                headers={"Content-Type": f"multipart/byteranges; boundary={BOUNDARY}"},
            )
            pct = (end + 1) * 100 // total
            show(f"    chunk {chunk_num}/{total_chunks} ({pct}%) -> HTTP {r.status_code}")
            if r.status_code not in (200, 204, 308):
                show(f"FATAL: chunk {chunk_num} failed: {r.text}")
                sys.exit(1)
            offset = end + 1


def activate(c):
    show("==> Activating WAGO Firmware Update")
    resp = run_method(
        c,
        "0-0-firmwareupdate-activate",
        {"KeepCustomerApplication": {"value": False}, "CustomKeyValuePairs": {"value": []}},
    )
    if method_ok(resp):
        show("    activated")
        return
    detail = resp.get("data", {}).get("attributes", {}).get("detail", "")
    if "90" in str(resp):  # already active
        show(f"    already active, continuing ({detail})")
        return
    show(f"FATAL: activate failed: {json.dumps(resp)}")
    show("Recent log:")
    for line in get_log_tail(c):
        show(f"    {line}")
    show(
        "\nCommon cause: /tmp/fwupdate on the device is missing or has the wrong "
        "owner/permissions. Fix via SSH:\n"
        "  mkdir -p /tmp/fwupdate && chgrp admin /tmp/fwupdate && chmod 770 /tmp/fwupdate"
    )
    sys.exit(1)


def get_upload_id(c, filename):
    resp = run_method(c, "0-0-firmwareupdate-getuploadids", {"FileNames": {"value": [filename]}})
    if not method_ok(resp):
        show(f"FATAL: could not reserve upload slot: {json.dumps(resp)}")
        sys.exit(1)
    return resp["data"]["attributes"]["outArgs"]["UploadFiles"]["value"][0]


def start(c, file_id):
    show("==> Starting update")
    resp = run_method(c, "0-0-firmwareupdate-start", {"UploadFiles": {"value": [file_id]}})
    if not method_ok(resp):
        show(f"FATAL: start failed: {json.dumps(resp)}")
        for line in get_log_tail(c):
            show(f"    {line}")
        sys.exit(1)


STATUS_UNCONFIRMED = 4  # RAUC install done, device rebooted into new slot,
                        # self-test passed. Progress plateaus at ~93% here
                        # PERMANENTLY - it never reaches 100 on its own.
                        # Finish() is what's needed to move past this, on
                        # every real device tested (WP400, two PFC200s).


def wait_for_completion(c):
    show("==> Waiting for install + auto-reboot (connection may drop briefly - this is normal)")
    deadline = time.time() + POLL_TIMEOUT
    last_seen = None
    while time.time() < deadline:
        time.sleep(POLL_INTERVAL)
        try:
            status_val, status_name = get_status(c)
            progress = get_progress(c)
        except (httpx.RequestError, httpx.HTTPStatusError, KeyError, json.JSONDecodeError):
            show("    [device unreachable - likely mid-reboot]")
            continue
        seen = (status_val, progress)
        if seen != last_seen:
            show(f"    fwstatus: {status_name} ({status_val})  progress: {progress}%")
            last_seen = seen
        if progress == 100 or status_val == STATUS_UNCONFIRMED:
            return
    show("FATAL: timed out waiting for the install to reach a finishable state")
    sys.exit(1)


def finish(c):
    show("==> Finishing update")
    resp = run_method(c, "0-0-firmwareupdate-finish")
    if not method_ok(resp):
        show(f"FATAL: finish failed: {json.dumps(resp)}")
        sys.exit(1)


def clear(c):
    show("==> Clearing update state")
    # The device may still be mid-way through its own auto runtime-restore
    # sequence right after Finish, during which Clear is rejected with
    # "Invalid clear request ... state confirmed". Retry briefly.
    deadline = time.time() + 60
    while time.time() < deadline:
        resp = run_method(c, "0-0-firmwareupdate-clear")
        if method_ok(resp):
            show("    cleared")
            return
        show("    not ready yet, retrying...")
        time.sleep(5)
    show(f"WARNING: clear did not succeed within 60s: {json.dumps(resp)}")


def main():
    show(f"WDA firmware update -> {PLC_IP}")
    show(f"Source .wup: {WUP_PATH}")
    if DRY_RUN:
        show("==> DRY_RUN=true: will upload the image and verify it, then stop BEFORE Start.")
        show("    No firmware will actually be flashed. Unset DRY_RUN to run for real.")

    if not Path(WUP_PATH).is_file():
        show(f"FATAL: {WUP_PATH} not found (check the WUP_FILE_PATH volume mount)")
        sys.exit(1)

    show("==> Extracting .raucb bundle")
    raucb_path = extract_raucb(WUP_PATH)
    show(f"    {raucb_path.name} ({raucb_path.stat().st_size} bytes)")

    with client() as c:
        activate(c)
        file_id = get_upload_id(c, raucb_path.name)
        show(f"    file_id={file_id}")
        upload_chunks(c, file_id, raucb_path)

        if DRY_RUN:
            show("==> DRY_RUN=true: stopping here. Cancelling the reserved update session.")
            run_method(c, "0-0-firmwareupdate-cancel")
            clear(c)  # retries internally; cancel leaves a transitional "revert"
                      # state that briefly rejects Clear, same as after Finish
            show("==> Dry run complete. Upload pipeline verified; Start was never called.")
            return

        start(c, file_id)
        wait_for_completion(c)
        finish(c)
        clear(c)

        status_val, status_name = get_status(c)
        fw_version = c.get(f"{BASE}/wda/parameters/0-0-version-firmwareversion").json()["data"]["attributes"]["value"]
        show(f"==> Done. fwstatus: {status_name} ({status_val})  firmware version: {fw_version}")


if __name__ == "__main__":
    main()
