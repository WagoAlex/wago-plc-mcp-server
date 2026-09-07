#!/usr/bin/env python3
"""
Deliver a WAGO .wup firmware image to a device via the WDA REST API and drive
the update to completion, printing live status/progress to stdout.

Verified live against a WP400 and a PFC200 G2 (both FW31, WDA 1.5.2).
See ../docs/wda-firmware-update.md for the full write-up of why each step
exists (Activate must precede Start, /tmp/fwupdate permission requirement,
the .raucb-not-.wup payload, the ~4MB chunk ceiling).

Two modes, chosen automatically:

  Catalog mode (default): mount a directory of .wup bundles at FIRMWARE_DIR.
  The script reads the device's own Identity/OrderNumber and current
  firmware version, builds a catalog from every package-info.xml in that
  directory (see catalog.py / build_catalog.py), and picks the bundle whose
  ArticleList lists the device's order number. Refuses to run if no bundle
  matches, if several match and TARGET_VERSION wasn't given, if the device
  is already at the target version, or if the current version falls outside
  the chosen bundle's own declared upgrade/downgrade range.

  Manual mode: set WUP_PATH to a specific file (inside the container) to
  bypass catalog resolution entirely and use exactly that bundle, no
  questions asked - the original single-file behavior.

Env vars:
    PLC_IP          required
    PLC_USERNAME    default "admin"
    PLC_PASSWORD    required
    FIRMWARE_DIR    default "/firmware" - directory of .wup bundles (catalog mode)
    TARGET_VERSION  optional, e.g. "4.9.1" - exact revision to require;
                     required when several bundles list the device's order number
    WUP_PATH        optional - an exact bundle path inside the container;
                     setting this skips catalog resolution entirely (manual mode)
    CHUNK_SIZE      default 4000000 (~4MB, the verified safe ceiling)
    POLL_INTERVAL   default 6 (seconds between status polls)
    AUDIT_LOG_FILE  path to the tamper-evident audit chain shared with the MCP
                     server and scripts/apply.py; unset disables audit writes
    POLL_TIMEOUT    default 900 (seconds to wait for a finishable state before giving up)
    HTTP_TIMEOUT    default 45 (seconds per HTTP request; the CC100 is the slow
                     one on this fleet and needs 45+, everything else is fine at ~15)
"""
import json
import os
import sys
import time
import zipfile
from pathlib import Path

import httpx

try:
    import audit  # the MCP server's own hash chain - one implementation, not a copy
except ModuleNotFoundError:  # running from a checkout rather than the container image
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
    import audit

import authz
import source
from catalog import build_catalog, read_bundle_metadata, resolve_bundle

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


# FWUErrorCauses, read live from a TP600 (WDA 1.5.2) via
# /wda/parameter-definitions/0-0-firmwareupdate-errorcause/enum.
# The hundreds digit is the phase that failed.
ERROR_CAUSES = {
    0: "NoError",
    100: "InternalError",
    101: "AbortByUser",
    102: "AbortInitializationFailed",
    103: "AbortCheckSystemFailed",
    200: "SignatureInvalid",
    300: "NotEnoughResources",
    301: "StopRuntimeFailed",
    400: "SettingsBackupFailed",
    401: "FirmwareBackupFailed",
    402: "UserBackupFailed",
    403: "SaveModifiedSettingsFailed",
    500: "SettingsRestoreFailed",
    600: "UpdateFailed",
    601: "SignatureTooNew",
    602: "SignatureTooOld",
    603: "PartitionError",
    604: "ErrorRevertNotSupported",
    700: "BootloaderUpdateFailed",
    800: "RestartFailed",
    900: "SelftestFailed",
    1000: "ConfirmationTimeout",
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
FIRMWARE_SOURCE = env("FIRMWARE_SOURCE", env("FIRMWARE_DIR", "/firmware"))
FIRMWARE_CACHE = env("FIRMWARE_CACHE", "/firmware-cache")
FW_POLICY_FILE = env("FW_POLICY_FILE", "/policy/firmware-policy.yaml")
# One-shot ops file (the reboot-style path). When set it replaces the fleet
# policy as the authorization: one file, one device, one revision.
FW_OPS_FILE = env("FW_OPS_FILE")
FW_AUTHZ = env("FW_AUTHZ", "on").lower() not in ("off", "0", "false", "no")
FW_ALLOW_REFLASH = env("FW_ALLOW_REFLASH", "false").lower() in ("1", "true", "yes")
TARGET_VERSION = env("TARGET_VERSION")
WUP_PATH = env("WUP_PATH")  # manual override; unset => catalog mode
CHUNK_SIZE = int(env("CHUNK_SIZE", "4000000"))
POLL_INTERVAL = int(env("POLL_INTERVAL", "6"))
POLL_TIMEOUT = int(env("POLL_TIMEOUT", "900"))
# 45s, not 30: the CC100 answers WDA far slower than the rest of the fleet and
# times out at 30 under load (mid-install especially). Raising the floor costs
# nothing on fast devices - it is a ceiling, not a delay.
HTTP_TIMEOUT = float(env("HTTP_TIMEOUT", "45"))
AUDIT_LOG_FILE = env("AUDIT_LOG_FILE", "/app/data/audit.log")
DRY_RUN = env("DRY_RUN", "false").lower() in ("1", "true", "yes")
BOUNDARY = "wdafwupdateboundary"

# Failed method runs carry a structured `domainSpecificStatusCode` (a string)
# alongside the generic WDA `code` - verified live on a TP600, WDA 1.5.2:
#   {"code":"26","domainSpecificStatusCode":"95","detail":"...could not be
#    invoked. (Could Not Invoke Method)","executionStatus":"error"}
# 95 = firmware update not activated. 90 = already active (documented in the
# original trace, not yet re-observed live - if Activate ever FATALs on a
# device that is genuinely already in update mode, check the printed
# domainSpecificStatusCode against this constant first).
FWU_ALREADY_ACTIVE = "90"

BASE = f"https://{PLC_IP}"


def show(msg):
    print(msg, flush=True)


def audit_record(result, **details):
    """Append one record to the shared tamper-evident chain. A firmware flash is
    the highest-consequence thing this fleet can do, so every outcome lands here
    - refusals included, since "who tried and was denied" is the half that
    matters after an incident. Never let a logging failure abort or mask a run."""
    if not AUDIT_LOG_FILE:
        return
    try:
        audit.append_audit(AUDIT_LOG_FILE, "firmware_update", PLC_IP, "fwupdate", result, **details)
    except Exception as e:
        print(f"[audit] WARNING: could not write audit record: {e}", file=sys.stderr)


def client():
    return httpx.Client(auth=(USERNAME, PASSWORD), verify=False, timeout=HTTP_TIMEOUT)


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
    val = get_param(c, "0-0-firmwareupdate-status")
    return val, STATUS_NAMES.get(val, f"Unknown({val})")


def get_progress(c):
    return get_param(c, "0-0-firmwareupdate-progress")


def get_param(c, param_id):
    return c.get(f"{BASE}/wda/parameters/{param_id}").json()["data"]["attributes"]["value"]


def show_failure_diagnostics(c):
    """Print why the device stopped. The REST error bodies say nothing useful;
    errorcause/debuginfo and the update log are where the real reason lives."""
    try:
        cause = get_param(c, "0-0-firmwareupdate-errorcause")
        show(f"    errorcause: {ERROR_CAUSES.get(cause, 'Unknown')} ({cause})")
        debug = get_param(c, "0-0-firmwareupdate-debuginfo")
        if debug:
            show(f"    debuginfo: {debug}")
        show(f"    revertable: {get_param(c, '0-0-firmwareupdate-revertable')}")
    except (httpx.RequestError, httpx.HTTPStatusError, KeyError, json.JSONDecodeError) as e:
        show(f"    (could not read diagnostic parameters: {e})")
    show("    Recent log:")
    for line in get_log_tail(c, 15):
        show(f"    {line}")


def get_identity(c):
    return get_param(c, "0-0-identity-ordernumber"), get_param(c, "0-0-version-firmwareversion")


def resolve_wup_path(c):
    """Catalog mode: identify the device, build the catalog from
    FIRMWARE_DIR, and pick the correct bundle. Returns a Path."""
    order_number, current_version = get_identity(c)
    show(f"==> Device identity: order={order_number}  current firmware={current_version}")

    show(f"==> Firmware source: {FIRMWARE_SOURCE}")
    try:
        firmware_dir = source.fetch(FIRMWARE_SOURCE, FIRMWARE_CACHE)
    except Exception as e:
        show(f"FATAL: cannot resolve FIRMWARE_SOURCE {FIRMWARE_SOURCE!r}: {e}")
        sys.exit(1)

    show(f"==> Building catalog from {firmware_dir}")
    catalog = build_catalog(firmware_dir)
    if not catalog["bundles"]:
        show(f"FATAL: no .wup files found in {firmware_dir}")
        sys.exit(1)
    show(f"    {len(catalog['bundles'])} bundle(s) found")

    try:
        bundle, direction = resolve_bundle(
            catalog, order_number, current_version, TARGET_VERSION, allow_reflash=FW_ALLOW_REFLASH
        )
    except ValueError as e:
        show(f"FATAL: {e}")
        sys.exit(1)

    show(
        f"==> Resolved: {bundle['wup_file']} "
        f"({direction} {current_version} -> {bundle['revision']}, build {bundle['release_index']})"
    )
    return firmware_dir / bundle["wup_file"], bundle["revision"]


def check_authorization(revision):
    """Refuse to flash unless a git-committed policy approves this exact
    (device, revision) pair. Returns the authorizing commit sha, or None when
    the gate is deliberately disabled."""
    if DRY_RUN:
        show("==> Authorization: skipped (DRY_RUN never calls Start, so nothing can be flashed)")
        return None
    if not FW_AUTHZ:
        show("==> Authorization: DISABLED via FW_AUTHZ=off - this flash is not git-authorized")
        audit_record("proceeding without git authorization", revision=revision, fw_authz="off")
        return None
    # FW_OPS_FILE, when set, REPLACES the fleet policy - it is the reboot-style
    # one-shot path. Falling back to the policy here would silently widen the
    # authorization from "this one operation" to "any standing fleet approval",
    # which is exactly the bug this comment exists to prevent recurring.
    source_file = FW_OPS_FILE or FW_POLICY_FILE
    try:
        if FW_OPS_FILE:
            sha, approved_by = authz.load_ops_authorization(FW_OPS_FILE, PLC_IP, revision)
        else:
            policy, commit = authz.load_policy(FW_POLICY_FILE)
            sha, approved_by = authz.authorize(policy, commit, PLC_IP, revision)
    except authz.NotAuthorized as e:
        show(f"FATAL: refused - {e}")
        audit_record(f"refused: {e}", revision=revision, authorization_file=source_file)
        sys.exit(1)
    signoff = f", signed off by {approved_by}" if approved_by else ""
    show(f"==> Authorized by commit {sha[:12]} ({source_file}){signoff}: {PLC_IP} -> {revision}")
    audit_record("authorized", revision=revision, commit=sha, approved_by=approved_by or None,
                 authorization_file=source_file)
    return sha


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
    attrs = resp.get("data", {}).get("attributes", {})
    detail = str(attrs.get("detail", ""))
    if str(attrs.get("domainSpecificStatusCode", "")) == FWU_ALREADY_ACTIVE:
        show(f"    already active, continuing ({detail})")
        return
    show(f"FATAL: activate failed (domain code {attrs.get('domainSpecificStatusCode')}): {json.dumps(resp)}")
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


STATUS_REVERT = 6       # Rolling back to the previous slot - the install failed.
STATUS_ERROR = 7        # Terminal failure; errorcause says why.
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
        if status_val in (STATUS_ERROR, STATUS_REVERT):
            show(f"FATAL: update failed - device reports {status_name} ({status_val})")
            cause = get_param(c, "0-0-firmwareupdate-errorcause")
            show_failure_diagnostics(c)
            audit_record(f"failed: device reports {status_name}", status=status_name,
                         errorcause=f"{ERROR_CAUSES.get(cause, 'Unknown')} ({cause})", progress=progress)
            sys.exit(1)
    show("FATAL: timed out waiting for the install to reach a finishable state")
    show_failure_diagnostics(c)
    audit_record("failed: timed out waiting for a finishable state", poll_timeout=POLL_TIMEOUT,
                 last_seen=str(last_seen))
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
    if DRY_RUN:
        show("==> DRY_RUN=true: will upload the image and verify it, then stop BEFORE Start.")
        show("    No firmware will actually be flashed. Unset DRY_RUN to run for real.")

    with client() as c:
        if WUP_PATH:
            show(f"==> Manual mode: WUP_PATH={WUP_PATH} (catalog resolution skipped)")
            wup_path = Path(WUP_PATH)
            if not wup_path.is_file():
                show(f"FATAL: {wup_path} not found (check the volume mount)")
                sys.exit(1)
            revision = read_bundle_metadata(wup_path)["revision"]
            bundle_file = wup_path.name
        else:
            wup_path, revision = resolve_wup_path(c)
            bundle_file = wup_path.name

        check_authorization(revision)

        show("==> Extracting .raucb bundle")
        raucb_path = extract_raucb(wup_path)
        show(f"    {raucb_path.name} ({raucb_path.stat().st_size} bytes)")

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
            audit_record("dry run ok (not flashed)", revision=revision, bundle=bundle_file)
            return

        start(c, file_id)
        wait_for_completion(c)
        finish(c)
        clear(c)

        status_val, status_name = get_status(c)
        fw_version = get_param(c, "0-0-version-firmwareversion")
        show(f"==> Done. fwstatus: {status_name} ({status_val})  firmware version: {fw_version}")
        audit_record("ok", revision=revision, bundle=bundle_file, firmware_version=fw_version,
                     status=status_name)


if __name__ == "__main__":
    # A flash that dies mid-run must still leave a trail - an update that was
    # started and never finished is exactly the state an incident review needs
    # to see, and it is the one a happy-path-only logger loses.
    try:
        main()
    except SystemExit:
        raise
    except BaseException as e:  # KeyboardInterrupt included: an aborted flash is a finding
        audit_record(f"aborted: {type(e).__name__}: {e}")
        raise
