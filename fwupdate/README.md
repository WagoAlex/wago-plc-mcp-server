# WDA Firmware Update — containerized

Runs the verified REST-API firmware update procedure (see
`../docs/wda-firmware-update.md`) inside a container, driven entirely by env
vars, with live status/progress printed to stdout as it runs.

## Catalog mode (default) — auto-detects hardware and picks the right bundle

Point `FIRMWARE_HOST_DIR` at a directory holding `.wup` bundles for any mix
of hardware (CC100, PFC100/200/300, Edge Controller/TP600, WP400 — whatever
you have). The container:

1. Reads the device's own `Identity/OrderNumber` and current firmware version
2. Builds a catalog from every bundle's own `package-info.xml` in that
   directory (`catalog.py` / `build_catalog.py`) — nothing is inferred from
   filenames
3. Picks the bundle whose `ArticleList` contains the device's order number —
   the highest-revision compatible one, or an exact match if
   `TARGET_VERSION` is set
4. Validates the device's current version falls within *that bundle's own*
   declared upgrade or downgrade range before touching anything
5. Refuses to run (no flash attempted) if: no bundle matches the device's
   order number, the device is already at the target version, or the
   current version is outside the bundle's declared range

```bash
cp _env .env
# edit .env: PLC_IP, PLC_PASSWORD, FIRMWARE_HOST_DIR (a directory of .wup files)

docker compose up --build
```

Example resolution output (real, from a live PFC300 that had never been
touched — the tool correctly identified it and picked its bundle with no
manual XML-reading):
```
==> Device identity: order=0750-8302  current firmware=04.08.09
==> Building catalog from /firmware
    6 bundle(s) found
==> Resolved: PFC-300-Linux_update_V040901_31_r9d0900aaed.wup (upgrade 04.08.09 -> 4.9.1, build 31)
```

To target a specific version instead of "latest compatible" (e.g. rolling
back, or holding at an older release while other devices move ahead), set
`TARGET_VERSION` to the exact revision string a bundle declares (check
`build_catalog.py <dir>` output for what's available):
```bash
TARGET_VERSION=4.9.1 docker compose up --build
```

## Manual mode — bypass the catalog

Set `WUP_PATH` to an exact file (a path *inside* the container, under
`/firmware/`) to skip catalog resolution entirely and use exactly that
bundle, no compatibility checks beyond what the device itself enforces:
```bash
WUP_PATH=/firmware/WP400-Linux_update_V040901_31_r9d0900aaed.wup docker compose up --build
```

## Dry run first, always

**Before running for real, validate with `DRY_RUN=true`.** This runs the full
Activate/upload/verify pipeline (including catalog resolution) and confirms
the image lands correctly, then cancels and clears the update session —
`Start` is never called, so nothing is flashed. Only run without `DRY_RUN`
once you've confirmed the dry run succeeds:

```bash
DRY_RUN=true docker compose up --build
```

`docker compose up` (without `DRY_RUN`) runs the *entire* flow unattended,
including `Start` — the step that actually writes the new image to flash.
Treat launching it with the same care as running the manual curl sequence
step-by-step; don't background it or pipe it through something that could
silently keep it running past a point you meant to stop at (ask me how I
know).

Progress streams live (`Activate` → upload chunks → `Start` → poll through the
device's auto-reboot → `Finish` → `Clear`), e.g. (real output from a live run):

```
    fwstatus: Started (3)  progress: 51%
    fwstatus: Started (3)  progress: 61%
    [device unreachable - likely mid-reboot]
    [device unreachable - likely mid-reboot]
    fwstatus: Started (3)  progress: 91%
    fwstatus: Unconfirmed (4)  progress: 93%
==> Finishing update
==> Clearing update state
    cleared
==> Done. fwstatus: Inactive (0)  firmware version: 04.09.01
```

**Progress plateaus at ~93% permanently** — it never reaches 100 on its own,
on any device tested (WP400, two PFC200 G2 units). `status` reaching
`Unconfirmed (4)` is the real completion signal; that's what the poll loop
actually waits for before calling `Finish`.

## Env vars

| Var | Required | Default | Notes |
|---|---|---|---|
| `PLC_IP` | yes | — | Device IP |
| `PLC_PASSWORD` | yes | — | |
| `PLC_USERNAME` | no | `admin` | |
| `FIRMWARE_HOST_DIR` | yes (catalog mode) | — | **Host** directory of `.wup` files, used by the compose volume mount |
| `TARGET_VERSION` | no | unset = latest compatible | Exact bundle revision to require, e.g. `4.9.1` |
| `WUP_PATH` | no | unset = catalog mode | Container-internal path to an exact bundle; setting this skips catalog resolution |
| `CHUNK_SIZE` | no | `4000000` | Bytes/chunk. ~4 MB is the verified safe ceiling — larger trips a `lighttpd` request-size cap independent of the app |
| `POLL_INTERVAL` | no | `6` | Seconds between status polls |
| `POLL_TIMEOUT` | no | `900` | Seconds to wait for the install to reach a finishable state (`status=Unconfirmed` or `progress=100`) before giving up |

## Rebuilding/inspecting the catalog standalone

```bash
python3 build_catalog.py /home/wago/Documents/mcp/fw
```
Prints every bundle's revision, build index, article count, and
upgrade/downgrade ranges — useful for checking what `TARGET_VERSION` values
are actually available before running the container.

## Known preconditions (device-side, not fixed by this container)

If `Activate` fails, the device's `/tmp/fwupdate` directory likely doesn't
exist with the right ownership. Fix once via SSH:
```bash
mkdir -p /tmp/fwupdate && chgrp admin /tmp/fwupdate && chmod 770 /tmp/fwupdate
```

`network_mode: host` is required — the container needs direct LAN access to
the PLC subnet.

## Fleet-wide notes

For updating many devices, run one container per device **sequentially**,
not in parallel — firmware updates hit device-specific quirks (the
`/tmp/fwupdate` permission issue, the `Finish`-on-`Unconfirmed` timing) that
are far easier to diagnose one at a time, and a batch of simultaneous
reboots multiplies the blast radius of any one undiscovered issue. A simple
shell loop over device IPs, `DRY_RUN=true` first for the whole batch, then a
second pass for real, is the safer default over building parallel
orchestration.
