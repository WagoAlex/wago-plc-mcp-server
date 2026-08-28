# WDA Firmware Update — containerized

Runs the verified REST-API firmware update procedure (see
`../docs/wda-firmware-update.md`) inside a container, driven entirely by env
vars, with live status/progress printed to stdout as it runs.

## Usage

```bash
cp _env .env
# edit .env: PLC_IP, PLC_PASSWORD, WUP_FILE_PATH (host path to the .wup file)

docker compose up --build
```

**Before running for real, validate with `DRY_RUN=true`.** This runs the full
Activate/upload/verify pipeline and confirms the image lands correctly, then
cancels and clears the update session — `Start` is never called, so nothing
is flashed. Only run without `DRY_RUN` once you've confirmed the dry run
succeeds:

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
| `WUP_FILE_PATH` | yes | — | **Host** path to the `.wup` file, used by the compose volume mount |
| `CHUNK_SIZE` | no | `4000000` | Bytes/chunk. ~4 MB is the verified safe ceiling — larger trips a `lighttpd` request-size cap independent of the app |
| `POLL_INTERVAL` | no | `6` | Seconds between status polls |
| `POLL_TIMEOUT` | no | `900` | Seconds to wait for the install to reach a finishable state (`status=Unconfirmed` or `progress=100`) before giving up |

## Known preconditions (device-side, not fixed by this container)

If `Activate` fails, the device's `/tmp/fwupdate` directory likely doesn't
exist with the right ownership. Fix once via SSH:
```bash
mkdir -p /tmp/fwupdate && chgrp admin /tmp/fwupdate && chmod 770 /tmp/fwupdate
```

`network_mode: host` is required — the container needs direct LAN access to
the PLC subnet.
