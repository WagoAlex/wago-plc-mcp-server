#!/usr/bin/env bash
# Deliver a WAGO .wup firmware image to a device via the WDA REST API and
# drive the update to completion. Verified live against a WP400 (FW31/WDA 1.5.2).
#
# Usage: wda_firmware_update.sh <plc-ip> <username> <password> <path-to.wup>
#
# What this does, in order (see docs/wda-firmware-update.md for why):
#   1. Unzip the .wup locally to get the raw .raucb bundle (paramd wants the
#      bundle, not the zip container).
#   2. Call FirmwareUpdate/Activate FIRST (opposite of the OpenAPI listing
#      order) - this requires /tmp/fwupdate on the device to exist as
#      root:admin 0770. If activation fails with "tmp folder doesn't match
#      requirements", ssh in and fix it once:
#        mkdir -p /tmp/fwupdate && chgrp admin /tmp/fwupdate && chmod 770 /tmp/fwupdate
#   3. GetUploadIDs, then chunk-upload the .raucb via PATCH multipart/byteranges
#      (~4 MB/chunk - larger trips a lighttpd request-size cap, independent of
#      the app, that returns 413 before the app ever sees the body).
#   4. FirmwareUpdate/Start with the uploaded file_id. RAUC writes the new
#      image to the inactive slot; the device then reboots into it on its own.
#   5. Poll status/progress until the device comes back and progress hits 100.
#   6. FirmwareUpdate/Finish, then FirmwareUpdate/Clear.
#
# No explicit Reboot/BeginReboot call is used or needed - the slot switch
# reboot happens automatically as part of Start.
set -euo pipefail

PLC="${1:?usage: $0 <plc-ip> <username> <password> <path-to.wup>}"
USER="${2:?}"
PASS="${3:?}"
WUP="${4:?}"
CHUNK_SIZE=4000000
BOUNDARY="wdafwupdateboundary$$"

api() { # api METHOD PATH [DATA]
  local method="$1" path="$2" data="${3:-}"
  if [[ -n "$data" ]]; then
    curl -sk -u "$USER:$PASS" -H "Content-Type: application/vnd.api+json" \
      -X "$method" "https://$PLC$path" -d "$data"
  else
    curl -sk -u "$USER:$PASS" -H "Content-Type: application/vnd.api+json" \
      -X "$method" "https://$PLC$path"
  fi
}

run_method() { # run_method method-id [json-inargs]
  local id="$1"
  local args="${2:-}"
  [[ -z "$args" ]] && args="{}"
  api POST "/wda/methods/$id/runs?result-behavior=sync" \
    "{\"data\":{\"type\":\"runs\",\"attributes\":{\"inArgs\":$args}}}"
}

log_tail() {
  run_method "0-0-firmwareupdate-getlastlogentries" '{"EntryCount":{"value":10}}' \
    | python3 -c 'import json,sys; [print(e) for e in json.load(sys.stdin)["data"]["attributes"]["outArgs"]["Entries"]["value"]]'
}

echo "==> Extracting .raucb from $WUP"
WORKDIR=$(mktemp -d)
unzip -oq "$WUP" -d "$WORKDIR"
RAUCB=$(find "$WORKDIR" -name '*.raucb' | head -1)
[[ -n "$RAUCB" ]] || { echo "No .raucb found inside $WUP"; exit 1; }
RAUCB_SIZE=$(stat -c%s "$RAUCB")
RAUCB_NAME=$(basename "$RAUCB")
echo "    $RAUCB_NAME ($RAUCB_SIZE bytes)"

echo "==> Activating WAGO Firmware Update (must precede Start)"
resp=$(run_method "0-0-firmwareupdate-activate" \
  '{"KeepCustomerApplication":{"value":false},"CustomKeyValuePairs":{"value":[]}}')
echo "$resp"
if echo "$resp" | grep -q '"executionStatus":"error"'; then
  echo
  echo "Activate failed. Common cause: /tmp/fwupdate on the device is missing"
  echo "or has the wrong owner/permissions. Fix via SSH:"
  echo "  mkdir -p /tmp/fwupdate && chgrp admin /tmp/fwupdate && chmod 770 /tmp/fwupdate"
  echo
  echo "Recent firmware-update log:"
  log_tail
  exit 1
fi

echo "==> Reserving upload slot"
resp=$(run_method "0-0-firmwareupdate-getuploadids" \
  "{\"FileNames\":{\"value\":[\"$RAUCB_NAME\"]}}")
echo "$resp"
FILE_ID=$(echo "$resp" | python3 -c 'import json,sys; print(json.load(sys.stdin)["data"]["attributes"]["outArgs"]["UploadFiles"]["value"][0])')
echo "    file_id=$FILE_ID"

echo "==> Uploading $RAUCB_SIZE bytes in ${CHUNK_SIZE}-byte chunks"
offset=0
chunk_num=0
total_chunks=$(( (RAUCB_SIZE + CHUNK_SIZE - 1) / CHUNK_SIZE ))
CHUNK_FILE="$WORKDIR/_chunk.bin"
MULTIPART_FILE="$WORKDIR/_multipart.bin"
while [[ $offset -lt $RAUCB_SIZE ]]; do
  remaining=$(( RAUCB_SIZE - offset ))
  this_size=$(( remaining < CHUNK_SIZE ? remaining : CHUNK_SIZE ))
  end=$(( offset + this_size - 1 ))
  chunk_num=$(( chunk_num + 1 ))

  dd if="$RAUCB" of="$CHUNK_FILE" bs=1M skip="$offset" count="$this_size" \
     iflag=skip_bytes,count_bytes status=none

  {
    printf -- "--%s\r\n" "$BOUNDARY"
    printf "Content-Type: application/octet-stream\r\n"
    printf "Content-Range: bytes %s-%s/%s\r\n" "$offset" "$end" "$RAUCB_SIZE"
    printf "\r\n"
    cat "$CHUNK_FILE"
    printf "\r\n--%s--\r\n" "$BOUNDARY"
  } > "$MULTIPART_FILE"

  code=$(curl -sk -u "$USER:$PASS" -o /dev/null -w "%{http_code}" \
    -X PATCH "https://$PLC/files/$FILE_ID" \
    --data-binary "@$MULTIPART_FILE" \
    -H "Content-Type: multipart/byteranges; boundary=$BOUNDARY")

  pct=$(( (end + 1) * 100 / RAUCB_SIZE ))
  echo "    chunk $chunk_num/$total_chunks (${pct}%) -> HTTP $code"
  if [[ "$code" != "204" && "$code" != "200" && "$code" != "308" ]]; then
    echo "Upload failed at chunk $chunk_num."
    exit 1
  fi
  offset=$(( end + 1 ))
done

echo "==> Starting update with uploaded file"
resp=$(run_method "0-0-firmwareupdate-start" \
  "{\"UploadFiles\":{\"value\":[\"$FILE_ID\"]}}")
echo "$resp"
if echo "$resp" | grep -q '"executionStatus":"error"'; then
  echo "Start failed:"
  log_tail
  exit 1
fi

echo "==> Waiting for install + auto-reboot (device drops off network mid-way - this is normal)"
for i in $(seq 1 120); do
  sleep 5
  status_json=$(curl -sk --max-time 5 -u "$USER:$PASS" "https://$PLC/wda/parameters/0-0-firmwareupdate-status" 2>/dev/null || true)
  progress_json=$(curl -sk --max-time 5 -u "$USER:$PASS" "https://$PLC/wda/parameters/0-0-firmwareupdate-progress" 2>/dev/null || true)
  status=$(echo "$status_json" | python3 -c 'import json,sys; print(json.load(sys.stdin)["data"]["attributes"]["value"])' 2>/dev/null || echo "?")
  progress=$(echo "$progress_json" | python3 -c 'import json,sys; print(json.load(sys.stdin)["data"]["attributes"]["value"])' 2>/dev/null || echo "?")
  echo "    [$i] status=$status progress=$progress"
  if [[ "$progress" == "100" ]]; then
    break
  fi
done

echo "==> Finishing update"
resp=$(run_method "0-0-firmwareupdate-finish")
echo "$resp"

echo "==> Clearing update state"
resp=$(run_method "0-0-firmwareupdate-clear")
echo "$resp"

echo "==> Done. Final log:"
log_tail

rm -rf "$WORKDIR"
