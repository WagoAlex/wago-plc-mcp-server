# WDA Firmware Update — Verified Procedure (REST API / curl)

**A full firmware update was executed end-to-end via the WDA REST API against a live
WP400 (192.168.2.136, FW build 31, WDA 1.5.2, order number 0762-3403) on 2026-08-28.**
The device went from `04.09.01(31)` back to `04.09.01(31)` (a re-flash, since that was
already the installed version) via `Activate` → upload → `Start` → auto-reboot →
`Finish` → `Clear`, confirmed against the device's own firmware-update log matching a
known-good historical update trace.

Method/parameter set confirmed identical across TP600 (192.168.2.174, 39 methods),
PFC300 (192.168.2.231, 33 methods), and WP400 (192.168.2.136, 39 methods) on FW31.

A ready-to-run implementation of everything below is at
`scripts/wda_firmware_update.sh <plc-ip> <username> <password> <path-to.wup>`.

> **Safety note:** every write method below is denylisted by `is_dangerous_method()`
> (`wago-quickref/SKILL.md`). In live mode the MCP server refuses these unless the exact
> method ID is in `WAGO_ALLOW_METHODS`; in GitOps mode they're proposed with
> `requires_human: CRITICAL`. The File API steps (`/files/...`) bypass `invoke_method`
> entirely and are not wrapped by any MCP tool — do those with raw HTTP/curl, as below.

## The corrected flow

The OpenAPI method listing order and a naive reading of the reference doc both suggest
`Start` before `Activate`. **That order is wrong in practice.** The verified sequence is:

| # | Step | Call | Notes |
|---|------|------|-------|
| 0 | Unzip `.wup` locally | — | A `.wup` is a ZIP of `package-info.xml` + a `.raucb` bundle. `fwupdate_control` on-device only understands the raw `.raucb` — uploading the `.wup` zip itself fails with `Unable to determine RAUC update file under "/tmp/fwupdate/"`. |
| 1 | **`Activate` first** | `POST /wda/methods/0-0-firmwareupdate-activate/runs` | `inArgs.KeepCustomerApplication` (bool), `inArgs.CustomKeyValuePairs` (string[]). Must precede `Start` — calling `Start` first fails with `WAGO Firmware Update not activated (95, state "inactive")`. |
| 2 | Reserve upload slot | `POST /wda/methods/0-0-firmwareupdate-getuploadids/runs` | `inArgs.FileNames`: `["<name>.raucb"]` → `outArgs.UploadFiles`: `[file_id]` |
| 3 | Chunk-upload the `.raucb` | `PATCH /files/{file_id}`, `multipart/byteranges` | ~4 MB/chunk max (see ceiling below). Verified with 75×4MB chunks over a ~283MB file, all `204`. |
| 4 | Start | `POST /wda/methods/0-0-firmwareupdate-start/runs` | `inArgs.UploadFiles`: `[file_id]`. RAUC writes the bundle to the inactive slot. |
| 5 | Wait — device reboots itself | — | Progress climbs (e.g. 51% → 93%), then the device **reboots into the new slot automatically** as part of this step. No explicit `Reboot/BeginReboot` call is used anywhere in the verified trace. Expect the HTTP connection to drop for ~20–30s during this. |
| 6 | Poll until 100% | `GET /wda/parameters/0-0-firmwareupdate-progress` | Resumes responding once the device is back up post-reboot. |
| 7 | Finish | `POST /wda/methods/0-0-firmwareupdate-finish/runs` | Marks the booted slot "good". |
| 8 | Clear | `POST /wda/methods/0-0-firmwareupdate-clear/runs` | Leaves update mode; `firmwareupdate-status` returns to `0` (idle). |

## Preconditions that aren't documented anywhere but matter

- **`Activate` requires `/tmp/fwupdate` to already exist as `root:admin`, mode `0770`.**
  On the WP400 tested, this directory did not exist and `fwupdate_background_service`
  does *not* create it correctly on its own — `Activate` failed with `fwupdate tmp
  folder doesn't match requirements!` until fixed manually:
  ```bash
  ssh admin@<plc-ip>
  mkdir -p /tmp/fwupdate
  chgrp admin /tmp/fwupdate
  chmod 770 /tmp/fwupdate
  ```
  The exact check (from `/usr/sbin/fwupdate_common`, function `fwupdate_check_tmp_folder`):
  ```bash
  find "$WAGO_FW_UPDATE_DEFAULT_TMP_DIR" -type d -user "root" -group "$WAGO_FW_UPDATE_GROUP" -perm 0770
  ```
  where `WAGO_FW_UPDATE_DEFAULT_TMP_DIR="/tmp/fwupdate"` and `WAGO_FW_UPDATE_GROUP="admin"`
  (from `/usr/sbin/fwupdate_basic_defines`). This is genuinely device-state-dependent —
  it may already be correct on a device that has been through a WBM-driven update before.

- **The chunked-upload `multipart/byteranges` body must exactly match the OpenAPI spec's
  own example** (each device serves its own spec at `/openapi/wda.openapi.json`):
  ```
  --{boundary}\r\n
  Content-Type: application/octet-stream\r\n
  Content-Range: bytes {start}-{end}/{total}\r\n
  \r\n
  {binary chunk}
  \r\n--{boundary}--\r\n
  ```
  A bare `Content-Type: application/octet-stream` with a `Content-Range` header
  (no multipart wrapper) gets `415`. Missing/unquoted-wrong boundary param gets `400`.

- **Chunk-size ceiling is ~4 MB, enforced by `lighttpd` in front of the app** (not
  `paramd`, the actual WDA/File-API backend process) — a whole-file `PUT` or an
  oversized `PATCH` chunk returns `413 Payload Too Large` in <0.2s, before any of the
  body is even read. This is independent of everything else on this list.

- **A `500 Internal Server Error` with an empty body from `PATCH /files/{id}`** is
  `paramd` failing to write the chunk to its backing file — confirmed via `strace -f -p
  <paramd-pid>` on-device, which surfaced the real internal error
  `{"Status":"FILE_NOT_ACCESSIBLE"}` and a syslog line `File write operation failed for
  file ID "..." (FILE_NOT_ACCESSIBLE)` that never reaches `/var/log/messages` on its own
  (paramd logs to syslog but nothing subscribes to that facility at a visible level by
  default). If you hit this, the `/tmp/fwupdate` precondition above is the fix.

## Escape hatches

| Method | Purpose |
|---|---|
| `0-0-firmwareupdate-cancel` | Abort an in-flight update |
| `0-0-firmwareupdate-clear` | Reset update state after an error/cancel, before retrying |
| `0-0-firmwareupdate-settimeout` | `inArgs.Timeout`: uint8 — extend the update-session timeout for a slow transfer |
| `0-0-firmwareupdate-setcustomvalue` / `-getcustomvalue` | `inArgs.Key`/`Value`: string — vendor-defined key/value pairs stored alongside the update session |
| `0-0-firmwareupdate-getlastlogentries` | `inArgs.EntryCount`: uint32 → `outArgs.Entries`: string[]. **The single most useful diagnostic call** — every `could_not_invoke_method` error's real cause showed up here, never in the REST error body itself. |

Not part of the upload-and-flash path — a separate image-duplication mechanism (SD card
backup/restore):
- `0-0-firmwareimage-copybootedimagetoexternalmedium` (`inArgs.Medium`, `inArgs.ImageSize`, both `enum_member`)
- `0-0-firmwareimage-copybootedimagetointernalmemory` (no inArgs)

## curl reference for each step

Set once:
```bash
PLC=192.168.2.136
PASS=wago   # or the device's real admin password
```

**1. Activate:**
```bash
curl -sk -u admin:$PASS -H "Content-Type: application/vnd.api+json" \
  -X POST "https://$PLC/wda/methods/0-0-firmwareupdate-activate/runs?result-behavior=sync" \
  -d '{"data":{"type":"runs","attributes":{"inArgs":{"KeepCustomerApplication":{"value":false},"CustomKeyValuePairs":{"value":[]}}}}}'
```

**2. Reserve upload slot:**
```bash
curl -sk -u admin:$PASS -H "Content-Type: application/vnd.api+json" \
  -X POST "https://$PLC/wda/methods/0-0-firmwareupdate-getuploadids/runs?result-behavior=sync" \
  -d '{"data":{"type":"runs","attributes":{"inArgs":{"FileNames":{"value":["update.raucb"]}}}}}'
# -> outArgs.UploadFiles.value[0] is your FILE_ID
```

**3. Upload one chunk** (repeat per chunk, incrementing the byte range; see
`scripts/wda_firmware_update.sh` for the full loop):
```bash
BOUNDARY=abcde12345
{
  printf -- "--%s\r\n" "$BOUNDARY"
  printf "Content-Type: application/octet-stream\r\n"
  printf "Content-Range: bytes %s-%s/%s\r\n" "$START" "$END" "$TOTAL"
  printf "\r\n"
  cat "$CHUNK_FILE"
  printf "\r\n--%s--\r\n" "$BOUNDARY"
} > /tmp/multipart.bin

curl -sk -u admin:$PASS -X PATCH "https://$PLC/files/$FILE_ID" \
  --data-binary "@/tmp/multipart.bin" \
  -H "Content-Type: multipart/byteranges; boundary=$BOUNDARY"
```

**4. Start:**
```bash
curl -sk -u admin:$PASS -H "Content-Type: application/vnd.api+json" \
  -X POST "https://$PLC/wda/methods/0-0-firmwareupdate-start/runs?result-behavior=sync" \
  -d "{\"data\":{\"type\":\"runs\",\"attributes\":{\"inArgs\":{\"UploadFiles\":{\"value\":[\"$FILE_ID\"]}}}}}"
```

**5/6. Poll:**
```bash
curl -sk -u admin:$PASS "https://$PLC/wda/parameters/0-0-firmwareupdate-status"
curl -sk -u admin:$PASS "https://$PLC/wda/parameters/0-0-firmwareupdate-progress"
```

**7. Finish:**
```bash
curl -sk -u admin:$PASS -H "Content-Type: application/vnd.api+json" \
  -X POST "https://$PLC/wda/methods/0-0-firmwareupdate-finish/runs?result-behavior=sync" \
  -d '{"data":{"type":"runs","attributes":{"inArgs":{}}}}'
```

**8. Clear:**
```bash
curl -sk -u admin:$PASS -H "Content-Type: application/vnd.api+json" \
  -X POST "https://$PLC/wda/methods/0-0-firmwareupdate-clear/runs?result-behavior=sync" \
  -d '{"data":{"type":"runs","attributes":{"inArgs":{}}}}'
```

**Diagnostics, any time:**
```bash
curl -sk -u admin:$PASS -H "Content-Type: application/vnd.api+json" \
  -X POST "https://$PLC/wda/methods/0-0-firmwareupdate-getlastlogentries/runs?result-behavior=sync" \
  -d '{"data":{"type":"runs","attributes":{"inArgs":{"EntryCount":{"value":15}}}}}'
```

## Gaps / caveats

- File API (`/files/...`) has no MCP tool wrapper — do the upload with raw
  `httpx`/`curl`, not `invoke_method`.
- All write-side methods above (`activate`, `start`, `finish`, `cancel`, `clear`,
  `settimeout`, `setcustomvalue`) need `WAGO_ALLOW_METHODS` opt-in per PLC to run
  through this MCP server in live mode; GitOps mode flags them `requires_human: CRITICAL`.
- The device's OpenAPI spec at `/openapi/wda.openapi.json` (per-device, authenticated
  GET) is the actual source of truth for the File API — more reliable than this
  project's static reference doc for anything upload-related, since it's generated from
  the live firmware build.
