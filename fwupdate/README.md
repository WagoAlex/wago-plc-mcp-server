# Firmware updates for WAGO controllers

Updates the firmware of WAGO PFC/CC/TP/WP devices over the WDA REST API, from a
container, with live progress on stdout. Verified on CC100, PFC200 G2, PFC300,
Edge Controller, TP600 and WP400.

It is a **separate tool from the MCP server on purpose**. The MCP server refuses
every firmware method so that an AI agent cannot flash a controller; this tool
is run by a person during a maintenance window, and refuses to start without an
approval committed to git.

---

## Quick start

```bash
cp _env .env
```

Fill in four things:

| Setting | Meaning |
|---|---|
| `PLC_IP`, `PLC_PASSWORD` | The device and its credentials |
| `FIRMWARE_SOURCE` | Where your `.wup` bundles live (directory, share, S3, HTTPS) |
| `POLICY_HOST_DIR` | Your config-repo checkout containing `firmware-policy.yaml` |
| `FIRMWARE_HOST_DIR` | Only for the default mounted-directory source |

Then, always in this order:

```bash
# 1. Rehearse. Uploads and verifies the image, then cancels.
#    Start is never called - nothing is flashed.
DRY_RUN=true docker compose up --build

# 2. One device, for real
docker compose up --build

# 3. Or every device your policy approves, one at a time
docker compose run --rm fleet
```

A run takes roughly 5-15 minutes per device, most of it upload and the
device's own reboot.

> **Do not walk away from step 2 or 3 the way you would from a build.** These
> steps write flash and reboot a controller. Run them in a window, watch the
> output, and never background them or pipe them into something that could keep
> them alive past the point you meant to stop.

---

## What can go wrong, and what the tool does about it

| Situation | What happens |
|---|---|
| Device not approved in git | Refused before the device is contacted |
| Approval edited but not committed | Refused - an uncommitted policy is not an authorization |
| Approval says a different revision than the bundle | Refused, both values named |
| Two bundles match the device | Refused and listed - never a guess |
| Device already at that version | Refused unless `FW_ALLOW_REFLASH=true` |
| Current version outside the bundle's declared range | Refused |
| Device rejects the image | Stops immediately, prints the device's own `errorcause` |
| Install never reaches a finishable state | Stops at `POLL_TIMEOUT` with diagnostics |

Every one of those outcomes is written to the audit log.

---

## Authorization lives in git, not in an env var

Flashing firmware is fleet-wide and hard to walk back, so "which device may go
to which revision" is not something a command line decides. It is a YAML file
committed to git:

```yaml
# firmware-policy.yaml
approvals:
  192.168.42.110: "4.9.1"    # CC100
  192.168.42.118: "4.9.1"    # PFC200 G2
  192.168.42.119: "4.9.1"    # PFC300
  192.168.2.136:  "4.9.1"    # WP400
  192.168.2.174:  "4.9.1"    # TP600
```

Before anything is flashed, the container refuses unless **all** of these hold:

1. the policy file is **tracked by git**
2. the working-tree copy is **identical to the committed one** - editing the
   file locally authorizes nothing
3. the device's IP is listed with the **exact revision** the resolved bundle
   declares
4. optionally (`FW_REQUIRE_SIGNED_COMMIT=true`) `HEAD` carries a **valid
   signature**

The authorizing commit sha is printed and can be audited afterwards with
`git show <sha>` - "who approved this flash" stays answerable:

```
==> Authorized by commit ce3877349fce (/policy/firmware-policy.yaml): 192.168.42.118 -> 4.9.1
```

Refusals name the reason and exit before touching the device:

```
FATAL: refused - 192.168.42.118 is approved for firmware 4.9.1, but the resolved
bundle is 4.9.50. Commit a policy change if 4.9.50 is what you want.
```

Mount the checkout (including its `.git`, which is what proves the commit) and
point `FW_POLICY_FILE` at the file:

```bash
POLICY_HOST_DIR=/home/wago/Documents/mcp/wago-plc-config docker compose up --build
```

`DRY_RUN=true` skips the gate on purpose - a dry run never calls `Start`, so
nothing can be flashed, and rehearsing *before* asking for approval is the
right order. `FW_AUTHZ=off` disables the gate entirely for one-off manual work;
it prints a loud notice, and any run that uses it is by definition not
git-authorized.

## Every run lands in the audit chain

A firmware flash is the highest-consequence thing this fleet can do, so it
writes to the **same tamper-evident hash chain** as the MCP server and
`scripts/apply.py` - not a separate log, and not a copy of the implementation:
the image builds `src/audit.py` straight from the server's source, and the
`../data:/app/data` mount is the same volume.

Every outcome is recorded, refusals included, because "who tried and was
denied" is the half that matters after an incident:

| `result` | When |
|---|---|
| `authorized` | The git gate passed - carries the commit sha and `approved_by` |
| `refused: ...` | Any gate refusal, with the reason verbatim |
| `ok` | Flash completed, with the resulting firmware version |
| `failed: device reports Error` | The device rejected it, with its own `errorcause` |
| `failed: timed out ...` | Never reached a finishable state |
| `aborted: ...` | The run died mid-flash - the state an incident review most needs |
| `dry run ok (not flashed)` | A rehearsal, explicitly marked as not a flash |
| `proceeding without git authorization` | `FW_AUTHZ=off` was used |

```json
{"ts": "2026-09-07T12:45:37Z", "action": "firmware_update", "plc": "192.168.42.111",
 "agent": "fwupdate", "result": "refused: 192.168.42.111 is not listed in the firmware policy",
 "prev": "7c49824b5eca...", "revision": "4.9.1", "policy_file": "/policy/firmware-policy.yaml"}
```

Verify the chain the same way as always:
```bash
docker exec wmcp python /app/src/audit_verify.py --log /app/data/audit.log
```

Passwords never reach the log - `audit.redact_details()` runs before hashing,
so the chain stays verifiable over exactly what is stored.

## The whole fleet in one command

`fleet.py` reads the same policy and updates every approved device
**sequentially**, one child process per device:

```bash
DRY_RUN=true docker compose run --rm fleet   # rehearse the whole fleet
docker compose run --rm fleet                # then run it for real
```

Sequential is deliberate: firmware updates hit device-specific quirks (the
`/tmp/fwupdate` permission requirement, the `Finish`-on-`Unconfirmed` timing)
that are much easier to diagnose one at a time, and a batch of simultaneous
reboots multiplies the blast radius of any single undiscovered issue. One
process per device also means a crash mid-run cannot poison the next. A failed
device is reported and the fleet continues; the summary at the end lists every
outcome, and the exit code is non-zero if any device failed.

Per-device passwords follow the MCP server's convention: a Docker secret at
`/run/secrets/plc_password_<ip_with_underscores>`, falling back to
`PLC_PASSWORD` for the whole fleet.

## Where bundles come from - `FIRMWARE_SOURCE`

Everything downstream (catalog resolution, upload, flash) only ever sees a
plain directory of `.wup` files, so the source is swappable:

| `FIRMWARE_SOURCE` | What it is |
|---|---|
| `/firmware` | A mounted directory - set `FIRMWARE_HOST_DIR` and use the compose mount |
| `file:///mnt/fwshare` | A network share (SMB/NFS) the **host** has already mounted - mounting is the OS's job, not this container's |
| `s3://bucket/firmware/` | An S3 bucket, or any S3-compatible store via `AWS_ENDPOINT_URL` (MinIO, Ceph). Standard AWS credential env vars |
| `https://host/path/PFC-G2_update_V040901.wup` | One bundle over HTTPS. **This is what a Teams / SharePoint / OneDrive share link is**, once you append `?download=1` to an "anyone with the link" URL |
| `https://host/path/index.json` | A manifest - the way to serve a whole multi-device bundle set over HTTPS from anywhere that hosts a static file |

Manifest format (`sha256` optional but checked when present):

```json
[
  {"name": "PFC-G2-Linux_update_V040901_31_r9d0900aaed.wup",
   "url":  "https://host/fw/PFC-G2-Linux_update_V040901_31_r9d0900aaed.wup",
   "sha256": "..."},
  {"name": "WP400-Linux_update_V040901_31_r9d0900aaed.wup",
   "url":  "https://host/fw/WP400-Linux_update_V040901_31_r9d0900aaed.wup"}
]
```

Sources behind auth (SharePoint with a token, Artifactory, a private bucket
gateway) take `FIRMWARE_SOURCE_TOKEN`, sent as `Authorization: Bearer`.

Remote bundles are cached in the `fwcache` volume by name and size, so a
re-run does not re-fetch ~200 MB files. Downloads are written to a `.part`
file and renamed only on success, so an interrupted transfer can never be
mistaken for a cached bundle. A `sha256` mismatch deletes the download and
aborts. Note that the `.wup` is WAGO-signed regardless - the device itself
rejects a corrupt or wrong-vintage image with `SignatureInvalid` /
`SignatureTooOld` - so these checks are the early, cheap backstop, not the
only one.

Resolve a source standalone to see what it yields, without touching a device:

```bash
docker compose run --rm --entrypoint python fwupdate source.py s3://my-bucket/fw /tmp/cache
```

## Catalog mode (default) - auto-detects hardware and picks the right bundle

Point `FIRMWARE_HOST_DIR` at a directory holding `.wup` bundles for any mix
of hardware (CC100, PFC100/200/300, Edge Controller/TP600, WP400 - whatever
you have). The container:

1. Reads the device's own `Identity/OrderNumber` and current firmware version
2. Builds a catalog from every bundle's own `package-info.xml` in that
   directory (`catalog.py` / `build_catalog.py`) - nothing is inferred from
   filenames
3. Picks the bundle whose `ArticleList` contains the device's order number.
   If exactly one bundle matches, it's used. If several do, the container
   **refuses and lists them** - set `TARGET_VERSION` to choose. It never
   guesses, because "highest revision" is not a safe tiebreak: WAGO's
   PFC-G2 `red-autoupdate` bundle carries a byte-identical `ArticleList`
   and a *higher* revision (4.9.50) than the standard 4.9.1 release, so
   "latest" would silently flash redundancy firmware onto a plain PFC200 G2
4. Validates the device's current version falls within *that bundle's own*
   declared upgrade or downgrade range before touching anything
5. Refuses to run (no flash attempted) if: no bundle matches the device's
   order number, several match and no `TARGET_VERSION` was given, the
   device is already at the target version, or the current version is
   outside the bundle's declared range

```bash
cp _env .env
# edit .env: PLC_IP, PLC_PASSWORD, FIRMWARE_HOST_DIR (a directory of .wup files)

docker compose up --build
```

Example resolution output (real, from a live PFC300 that had never been
touched - the tool correctly identified it and picked its bundle with no
manual XML-reading):
```
==> Device identity: order=0750-8302  current firmware=04.08.09
==> Building catalog from /firmware
    6 bundle(s) found
==> Resolved: PFC-300-Linux_update_V040901_31_r9d0900aaed.wup (upgrade 04.08.09 -> 4.9.1, build 31)
```

`TARGET_VERSION` is what you set to disambiguate, to roll back, or to hold
a device at an older release while others move ahead. It takes the exact
revision string a bundle declares (run `build_catalog.py <dir>` to see
what's available):
```bash
TARGET_VERSION=4.9.1 docker compose up --build
```

## Manual mode - bypass the catalog

Set `WUP_PATH` to an exact file (a path *inside* the container, under
`/firmware/`) to skip catalog resolution entirely and use exactly that
bundle, no compatibility checks beyond what the device itself enforces:
```bash
WUP_PATH=/firmware/WP400-Linux_update_V040901_31_r9d0900aaed.wup docker compose up --build
```

## What a run looks like

A dry run (`DRY_RUN=true`) performs catalog resolution, `Activate`, the full
chunked upload and the device-side verification, then cancels and clears the
session. `Start` - the step that writes flash - is never called. Use it on
every device class you have not flashed before.

A real run streams progress live (`Activate` → upload chunks → `Start` → poll through the
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

**Progress plateaus at ~93% permanently** - it never reaches 100 on its own,
on any device tested (WP400, two PFC200 G2 units). `status` reaching
`Unconfirmed (4)` is the real completion signal; that's what the poll loop
actually waits for before calling `Finish`.

## When an update fails

The container stops as soon as `status` reaches `Error (7)` or `Revert (6)` - it does
not wait out `POLL_TIMEOUT` - and prints what the device itself says went wrong:

```
FATAL: update failed - device reports Error (7)
    errorcause: SignatureTooOld (602)
    debuginfo: ...
    revertable: True
    Recent log:
    ...
```

`errorcause` is the useful field; the hundreds digit is the phase that failed
(2xx signature, 3xx resources, 4xx backup, 6xx the RAUC install itself, 900 self-test,
1000 confirmation timeout). Full table: `docs/wda-firmware-update.md`.

## Env vars

| Var | Required | Default | Notes |
|---|---|---|---|
| `PLC_IP` | yes | - | Device IP |
| `PLC_PASSWORD` | yes | - | |
| `PLC_USERNAME` | no | `admin` | |
| `FIRMWARE_SOURCE` | no | `/firmware` | Where bundles come from: a path, `file://`, `s3://` or `https://` (see above) |
| `FIRMWARE_HOST_DIR` | yes for the default mounted-directory source | - | **Host** directory of `.wup` files, used by the compose volume mount |
| `FIRMWARE_CACHE` | no | `/firmware-cache` | Where remote sources are synced to |
| `FIRMWARE_SOURCE_TOKEN` | no | unset | Bearer token for an HTTPS source behind auth |
| `POLICY_HOST_DIR` | yes unless `FW_AUTHZ=off` | `.` | **Host** path of the git checkout holding the policy, mounted at `/policy` |
| `FW_POLICY_FILE` | no | `/policy/firmware-policy.yaml` | Git-committed approvals file |
| `FW_AUTHZ` | no | `on` | `off` disables the git gate entirely (loudly) |
| `FW_REQUIRE_SIGNED_COMMIT` | no | `false` | Also require a valid signature on `HEAD` |
| `TARGET_VERSION` | no | unset = require a single match | Exact bundle revision to require, e.g. `4.9.1`. Needed whenever more than one bundle in the directory lists the device's order number |
| `WUP_PATH` | no | unset = catalog mode | Container-internal path to an exact bundle; setting this skips catalog resolution |
| `CHUNK_SIZE` | no | `4000000` | Bytes/chunk. ~4 MB is the verified safe ceiling - larger trips a `lighttpd` request-size cap independent of the app |
| `POLL_INTERVAL` | no | `6` | Seconds between status polls |
| `HTTP_TIMEOUT` | no | `45` | Seconds per HTTP request. The CC100 needs 45+; it times out at 30 mid-install. A ceiling, not a delay |
| `FW_ALLOW_REFLASH` | no | `false` | Write the version the device already runs (still range-checked) |
| `WAGO_APPROVED_BY` | no | unset | Lets CI supply `approved_by` for a review-gated entry, as `scripts/apply.py` does |
| `AUDIT_LOG_FILE` | no | `/app/data/audit.log` | Shared tamper-evident chain; empty disables audit writes |
| `POLL_TIMEOUT` | no | `900` | Seconds to wait for the install to reach a finishable state (`status=Unconfirmed` or `progress=100`) before giving up |

## Rebuilding/inspecting the catalog standalone

```bash
python3 build_catalog.py /home/wago/Documents/mcp/fw
```
Prints every bundle's revision, build index, article count, and
upgrade/downgrade ranges - useful for checking what `TARGET_VERSION` values
are actually available before running the container.

## Known preconditions (device-side, not fixed by this container)

If `Activate` fails, the device's `/tmp/fwupdate` directory likely doesn't
exist with the right ownership. Fix once via SSH:
```bash
mkdir -p /tmp/fwupdate && chgrp admin /tmp/fwupdate && chmod 770 /tmp/fwupdate
```

`network_mode: host` is required - the container needs direct LAN access to
the PLC subnet.

## Running this securely

The tool is designed to be run by a person, on a maintenance host, against a
segmented OT network. The points below are what an auditor will ask about.

**Credentials.** Prefer Docker secrets over `.env`. A per-device secret at
`/run/secrets/plc_password_<ip_with_underscores>` is used automatically in
fleet mode, falling back to `PLC_PASSWORD`. Passwords are never written to the
audit log: `audit.redact_details()` runs before hashing, so the chain stays
verifiable over exactly what is stored.

**Network placement.** Run on a host that already has a route to the PLC
subnets (`network_mode: host` is required). The container needs no inbound
access and no internet access, unless you point `FIRMWARE_SOURCE` at a remote
bundle store.

**Bundle integrity.** `.wup` bundles are signed by WAGO and the device rejects a
wrong or tampered image itself (`SignatureInvalid`, `SignatureTooOld`). An
HTTPS manifest can additionally carry a `sha256` per bundle, which is verified
before the file is accepted into the cache. Interrupted downloads are written
to a `.part` file and never mistaken for a complete bundle.

**Approval integrity.** For regulated environments set
`FW_REQUIRE_SIGNED_COMMIT=true`, which additionally requires `git verify-commit
HEAD` to pass. Mount the policy checkout read-only (`:ro`) - the tool only ever
reads it.

**Separation of duties.** The person who proposes an approval and the person
who sets `approved_by` need not be the same; enforce that with branch
protection and required reviewers on your config repository, the same way you
already do for `ops/` files.

**Escape hatches, and when not to use them.** `FW_AUTHZ=off` disables the git
gate and `FW_ALLOW_REFLASH=true` permits writing a version the device already
runs. Both print a notice and both are recorded in the audit log. `FW_AUTHZ=off`
is for bench work on a device that is not part of a managed fleet; a run that
uses it is, by definition, not authorized.

---

## Verifying the trail afterwards

```bash
# Was the chain tampered with?
docker exec wmcp python /app/src/audit_verify.py --log /app/data/audit.log

# What did this fleet's firmware activity look like?
grep firmware_update data/audit.log | python3 -m json.tool

# Who approved a given flash?
git -C /path/to/wago-plc-config show <commit-from-the-audit-record>
```
