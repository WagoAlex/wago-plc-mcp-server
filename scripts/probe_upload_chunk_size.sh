#!/usr/bin/env bash
# Probe the max chunk size /files/{file_id} PATCH accepts on this WDA build.
# Requires PLC, PASS, FILE_ID, WUP already exported in the shell.
set -u

BOUNDARY="WDA_FILE_BOUNDARY_8f3a1c"
TOTAL=$(stat -c%s "$WUP")
TMPDIR=$(mktemp -d)

try_size() {
  local size=$1
  local end=$((size - 1))
  dd if="$WUP" of="$TMPDIR/chunk.bin" bs="$size" count=1 status=none 2>/dev/null

  {
    printf -- "--%s\r\n" "$BOUNDARY"
    printf "Content-Type: application/octet-stream\r\n"
    printf "Content-Range: bytes 0-%s/%s\r\n" "$end" "$TOTAL"
    printf "\r\n"
    cat "$TMPDIR/chunk.bin"
    printf "\r\n--%s--\r\n" "$BOUNDARY"
  } > "$TMPDIR/multipart.bin"

  local code
  code=$(curl -sk -u "admin:$PASS" -o "$TMPDIR/resp.html" -w "%{http_code}" \
    -X PATCH "https://$PLC/files/$FILE_ID" \
    --data-binary "@$TMPDIR/multipart.bin" \
    -H "Content-Type: multipart/byteranges; boundary=$BOUNDARY")
  echo "$code"
}

echo "Binary-searching max accepted chunk size against $PLC ..."
LOW=1024        # 1 KiB, assumed to work
HIGH=4194304    # 4 MiB, known to fail (413)
BEST=0

code=$(try_size "$LOW")
echo "  $LOW bytes -> HTTP $code"
if [ "$code" != "200" ] && [ "$code" != "204" ] && [ "$code" != "308" ]; then
  echo "Even $LOW bytes failed (HTTP $code). Dumping response:"
  cat "$TMPDIR/resp.html"
  echo
  echo "Not a simple size ceiling — inspect response above."
  rm -rf "$TMPDIR"
  exit 1
fi
BEST=$LOW

while [ $((HIGH - LOW)) -gt 1024 ]; do
  MID=$(( (LOW + HIGH) / 2 ))
  code=$(try_size "$MID")
  echo "  $MID bytes -> HTTP $code"
  if [ "$code" = "200" ] || [ "$code" = "204" ] || [ "$code" = "308" ]; then
    LOW=$MID
    BEST=$MID
  else
    HIGH=$MID
  fi
done

echo
echo "Largest accepted chunk size found: $BEST bytes"
rm -rf "$TMPDIR"
