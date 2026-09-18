# WDA firmware update - tested procedure (REST API and curl)

This page is a reference for developers. For the normal procedure, use the `fwupdate` tool.
See [Firmware updates](firmware-updates.md).

> [!IMPORTANT]
> This procedure is for PTXdist PLCs (firmware 04.x, build 31) with the `FirmwareUpdate` feature.
> The CC100-IEC62443 (Yocto, firmware 02.x) uses the `Update` feature (`0-0-update-*`). Its procedure is different.

**On 2026-08-28, we did a full firmware update with the WDA REST API on a live WP400**
(192.168.2.136, build 31, WDA 1.5.2, order number 0762-3403).
The device already had `04.09.01(31)`, so the update installed the same version again.
The sequence was `Activate` → upload → `Start` → automatic reboot → `Finish` → `Clear`.
The firmware-update log of the device agreed with the log of an earlier successful update.

The methods and parameters are the same on the TP600 (192.168.2.174, 39 methods),
the PFC300 (192.168.2.231, 33 methods), and the WP400 (192.168.2.136, 39 methods) with build 31.

The script `scripts/wda_firmware_update.sh <plc-ip> <username> <password> <path-to.wup>` does all the steps below.

> **Safety note:** `is_dangerous_method()` in `src/safety.py` blocks each write method on this page.
> In live mode, the MCP server refuses them, unless the exact method ID is in `WAGO_ALLOW_METHODS`.
> In GitOps mode, the server proposes them with `requires_human: CRITICAL`.
> No MCP tool does the File API steps (`/files/...`), and `invoke_method` does not do them. Use HTTP or curl, as shown below.

## The correct sequence

The OpenAPI method list, and a quick reading of the reference document, both show `Start` before `Activate`.
**That order is wrong.** This is the tested sequence:

| # | Step | Call | Notes |
|---|------|------|-------|
| 0 | Unzip the `.wup` file on your computer | - | A `.wup` file is a ZIP file with `package-info.xml` and a `.raucb` bundle. `fwupdate_control` on the device accepts only the `.raucb` file. If you upload the `.wup` file, the update fails with `Unable to determine RAUC update file under "/tmp/fwupdate/"`. |
| 1 | **`Activate` first** | `POST /wda/methods/0-0-firmwareupdate-activate/runs` | `inArgs.KeepCustomerApplication` (bool), `inArgs.CustomKeyValuePairs` (string[]). Call it before `Start`. If you call `Start` first, the run fails with `domainSpecificStatusCode` `95` (update not activated). |
| 2 | Get an upload ID | `POST /wda/methods/0-0-firmwareupdate-getuploadids/runs` | `inArgs.FileNames`: `["<name>.raucb"]` → `outArgs.UploadFiles`: `[file_id]` |
| 3 | Upload the `.raucb` file in chunks | `PATCH /files/{file_id}`, `multipart/byteranges` | Maximum about 4 MB for each chunk (see the limit below). Tested with 75 chunks of 4 MB for a file of about 283 MB. All chunks returned `204`. |
| 4 | Start | `POST /wda/methods/0-0-firmwareupdate-start/runs` | `inArgs.UploadFiles`: `[file_id]`. RAUC writes the bundle to the inactive slot. |
| 5 | Wait - the device restarts | - | The progress increases, for example from 51% to 93%. Then the device **restarts into the new slot**. This is part of the step. The tested sequence has no `Reboot/BeginReboot` call. The HTTP connection stops for about 20-30 s. |
| 6 | Poll the status | `GET /wda/parameters/0-0-firmwareupdate-status` | After the restart, the device answers again. Continue when the status is `4` (Unconfirmed). The progress often stops at about 93%, so do not wait for 100%. |
| 7 | Finish | `POST /wda/methods/0-0-firmwareupdate-finish/runs` | Marks the booted slot as "good". |
| 8 | Clear | `POST /wda/methods/0-0-firmwareupdate-clear/runs` | Stops the update mode. `firmwareupdate-status` goes back to `0` (Inactive). |

## Preconditions that are not documented

- **`Activate` needs the directory `/tmp/fwupdate`, with owner `root:admin` and mode `0770`.**
  On the tested WP400, this directory did not exist, and `fwupdate_background_service` did not make it correctly.
  `Activate` failed with `fwupdate tmp folder doesn't match requirements!` until we made the directory by hand:
  ```bash
  ssh admin@<plc-ip>
  mkdir -p /tmp/fwupdate
  chgrp admin /tmp/fwupdate
  chmod 770 /tmp/fwupdate
  ```
  This is the check in `/usr/sbin/fwupdate_common`, function `fwupdate_check_tmp_folder`:
  ```bash
  find "$WAGO_FW_UPDATE_DEFAULT_TMP_DIR" -type d -user "root" -group "$WAGO_FW_UPDATE_GROUP" -perm 0770
  ```
  `WAGO_FW_UPDATE_DEFAULT_TMP_DIR="/tmp/fwupdate"` and `WAGO_FW_UPDATE_GROUP="admin"` come from `/usr/sbin/fwupdate_basic_defines`.
  The result depends on the device. A device that had an update from the WBM before can already have the correct directory.

- **The `multipart/byteranges` body must be the same as the example in the OpenAPI specification.**
  Each device supplies its own specification at `/openapi/wda.openapi.json`.
  ```
  --{boundary}\r\n
  Content-Type: application/octet-stream\r\n
  Content-Range: bytes {start}-{end}/{total}\r\n
  \r\n
  {binary chunk}
  \r\n--{boundary}--\r\n
  ```
  A body with only `Content-Type: application/octet-stream` and a `Content-Range` header, without the multipart wrapper, returns `415`.
  A missing or wrong `boundary` parameter returns `400`.

- **The limit for one chunk is about 4 MB. `lighttpd` in front of the application enforces it,** not `paramd` (the WDA and File API process).
  A `PUT` of the full file returns `413 Payload Too Large`. A `PATCH` chunk that is too large returns the same error.
  The error comes in less than 0.2 s, before the server reads the body.
  This limit is independent of the other items in this list.

- **A `500 Internal Server Error` with an empty body from `PATCH /files/{id}`** means that `paramd` could not write the chunk to its file.
  We found this with `strace -f -p <paramd-pid>` on the device. It showed the internal error `{"Status":"FILE_NOT_ACCESSIBLE"}`
  and the syslog line `File write operation failed for file ID "..." (FILE_NOT_ACCESSIBLE)`.
  This line does not appear in `/var/log/messages`, because by default no visible log level receives this syslog facility.
  If you get this error, make the `/tmp/fwupdate` directory as described above.

## The WDA parameters of the update

Six parameters show the update. They have the same `id`, `path`, and `dataType` on all six device classes
(CC100, PFC200 G2, PFC300, Edge Controller, TP600, WP400). We checked this in each FW31 cassette in `docs/*-fw31-parameters-raw.json`.
All six are **read-only**. You cannot control an update with a parameter. Each change of state needs a `0-0-firmwareupdate-*` method.

| Parameter ID | Path | Type | Used by `fwupdate/` | Meaning |
|---|---|---|---|---|
| `0-0-firmwareupdate-status` | `FirmwareUpdate/Status` | `enum_member` (`FWUStatus`) | yes - the completion signal | Position in the update state machine |
| `0-0-firmwareupdate-progress` | `FirmwareUpdate/Progress` | `uint8` | yes - display only | 0-100. **It often stops at about 93 and does not reach 100** |
| `0-0-firmwareupdate-errorcause` | `FirmwareUpdate/ErrorCause` | `enum_member` (`FWUErrorCauses`) | yes - after a failure | Why the update failed |
| `0-0-firmwareupdate-revertable` | `FirmwareUpdate/Revertable` | `boolean` | yes - after a failure | `true` if a return to the previous slot is possible |
| `0-0-firmwareupdate-debuginfo` | `FirmwareUpdate/DebugInfo` | `string` | yes - after a failure | Diagnostic text. `""` when no update runs |
| `0-0-firmwareimage-bootmedium` | `FirmwareImage/BootMedium` | `enum_member` | **no** | `0` InternalMemory, `1` MemoryCard |

The catalog mode also reads `0-0-version-firmwareversion` (`string`, for example `04.09.01`)
and `0-0-identity-ordernumber` to select a bundle.

### Enum members (read from a TP600, WDA 1.5.2)

We read these values from the device, not from a document. The enum is one step after the parameter definition:
```bash
curl -sk -L -u admin:$PASS -H "Accept: application/vnd.api+json" \
  "https://$PLC/wda/parameter-definitions/0-0-firmwareupdate-status/enum"
```
Use `-L`. `/wda/parameters/{id}/definition` answers with a `301` redirect to
`/wda/parameter-definitions/{id}`. Without `-L`, curl shows nothing.

**`FWUStatus`** - the same values as `STATUS_NAMES` in `fwupdate/fw_update.py`:

| Value | Name | | Value | Name |
|---|---|---|---|---|
| 0 | Inactive | | 5 | Confirmed |
| 1 | Init | | 6 | Revert |
| 2 | Prepared | | 7 | **Error** |
| 3 | Started | | 8 | Finished |
| 4 | **Unconfirmed** ← call `Finish` now | | 9 | NotAvailable |

**`FWUErrorCauses`** - the groups show in which phase the update failed:

| Value | Name | | Value | Name |
|---|---|---|---|---|
| 0 | NoError | | 403 | SaveModifiedSettingsFailed |
| 100 | InternalError | | 500 | SettingsRestoreFailed |
| 101 | AbortByUser | | 600 | UpdateFailed |
| 102 | AbortInitializationFailed | | 601 | SignatureTooNew |
| 103 | AbortCheckSystemFailed | | 602 | SignatureTooOld |
| 200 | SignatureInvalid | | 603 | PartitionError |
| 300 | NotEnoughResources | | 604 | ErrorRevertNotSupported |
| 301 | StopRuntimeFailed | | 700 | BootloaderUpdateFailed |
| 400 | SettingsBackupFailed | | 800 | RestartFailed |
| 401 | FirmwareBackupFailed | | 900 | SelftestFailed |
| 402 | UserBackupFailed | | 1000 | ConfirmationTimeout |

The hundreds digit is the phase:
1xx abort or initialization, 2xx signature, 3xx resources or runtime, 4xx backup, 5xx restore,
6xx the RAUC installation, 7xx bootloader, 8xx restart, 9xx self-test, and 1000 the end of the confirmation time.

Both drivers stop immediately when the status is `7` (Error) or `6` (Revert). They do not wait for `POLL_TIMEOUT`.
They show the name of the `errorcause`, the `debuginfo`, `revertable`, and the last 15 entries of the update log.
`ERROR_CAUSES` in `fwupdate/fw_update.py` is the same as this table.

### Errors from a method run

A failed method run returns **HTTP 200** with `executionStatus: "error"`. Always check the body, not the status code.
We tested this with a harmless call: `GetCustomValue` with a key that does not exist.

```json
{"data":{"attributes":{
  "executionStatus":"error",
  "code":"26",
  "domainSpecificStatusCode":"95",
  "title":"Failed to complete method run",
  "detail":"A domain specific error occurred on method run with ID \"1\". Associated
            method with ID \"0-0-firmwareupdate-getcustomvalue\" could not be
            invoked. (Could Not Invoke Method)"}}}
```

There are two different code systems:
- **`code`** is the general WDA status code (`26` = Could Not Invoke Method). Almost every firmware-update failure returns this same `26`. It tells you almost nothing.
- **`domainSpecificStatusCode`** is the code of the firmware update. `95` = update not activated. `90` = update already active. **Use this field to decide what to do.** It is a *string*, and successful runs do not have it.
- **`detail`** does *not* contain the domain code. Do not parse it.

The `FWUErrorCauses` above and the `domainSpecificStatusCode` are not related.
`FWUErrorCauses` describes an installation that started and then failed.
`domainSpecificStatusCode` describes a method call that the device refused before anything started.

## Methods for recovery and diagnostics

| Method | Purpose |
|---|---|
| `0-0-firmwareupdate-cancel` | Stops an update that runs |
| `0-0-firmwareupdate-clear` | Resets the update state after an error or a cancel. Use it before you try again |
| `0-0-firmwareupdate-settimeout` | `inArgs.Timeout`: uint8. Makes the update session longer for a slow transfer |
| `0-0-firmwareupdate-setcustomvalue` / `-getcustomvalue` | `inArgs.Key`/`Value`: string. Key/value pairs that the vendor defines. The device keeps them with the update session |
| `0-0-firmwareupdate-getlastlogentries` | `inArgs.EntryCount`: uint32 → `outArgs.Entries`: string[]. **This is the most useful diagnostic call.** For each `could_not_invoke_method` error, the real cause was in this log, never in the REST error body |

These methods are not part of the upload and flash sequence. They copy the firmware image, for example to an SD card as a backup:
- `0-0-firmwareimage-copybootedimagetoexternalmedium` (`inArgs.Medium`, `inArgs.ImageSize`, both `enum_member`)
- `0-0-firmwareimage-copybootedimagetointernalmemory` (no inArgs)

## curl commands for each step

Set these variables one time:
```bash
PLC=192.168.2.136
PASS=wago   # or the real admin password of the device
```

**1. Activate:**
```bash
curl -sk -u admin:$PASS -H "Content-Type: application/vnd.api+json" \
  -X POST "https://$PLC/wda/methods/0-0-firmwareupdate-activate/runs?result-behavior=sync" \
  -d '{"data":{"type":"runs","attributes":{"inArgs":{"KeepCustomerApplication":{"value":false},"CustomKeyValuePairs":{"value":[]}}}}}'
```

**2. Get an upload ID:**
```bash
curl -sk -u admin:$PASS -H "Content-Type: application/vnd.api+json" \
  -X POST "https://$PLC/wda/methods/0-0-firmwareupdate-getuploadids/runs?result-behavior=sync" \
  -d '{"data":{"type":"runs","attributes":{"inArgs":{"FileNames":{"value":["update.raucb"]}}}}}'
# -> outArgs.UploadFiles.value[0] is your FILE_ID
```

**3. Upload one chunk.** Do this for each chunk, with the next byte range.
For the full loop, see `scripts/wda_firmware_update.sh`.
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

**5 and 6. Poll:**
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

**Diagnostics, at any time:**
```bash
curl -sk -u admin:$PASS -H "Content-Type: application/vnd.api+json" \
  -X POST "https://$PLC/wda/methods/0-0-firmwareupdate-getlastlogentries/runs?result-behavior=sync" \
  -d '{"data":{"type":"runs","attributes":{"inArgs":{"EntryCount":{"value":15}}}}}'
```

## Limits

- No MCP tool does the File API calls (`/files/...`). Upload with `httpx` or `curl`, not with `invoke_method`.
- To run the write methods on this page (`activate`, `start`, `finish`, `cancel`, `clear`,
  `settimeout`, `setcustomvalue`) through this MCP server in live mode, add each one to `WAGO_ALLOW_METHODS`.
  In GitOps mode, the server proposes them with `requires_human: CRITICAL`.
- For the File API, the OpenAPI specification of the device at `/openapi/wda.openapi.json` is the most reliable source.
  Each device supplies it (authenticated GET), and the live firmware build generates it.
  It is more reliable than the static reference document of this project.
