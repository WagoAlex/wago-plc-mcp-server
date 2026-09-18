# Firmware updates for WAGO PLCs

This tool updates the firmware of WAGO PFC, CC, TP, and WP devices with the WDA REST API.
It runs in a container and shows the progress on stdout.
We tested it on the CC100, PFC200 G2, PFC300, Edge Controller, TP600, and WP400.

This tool is **separate from the MCP server on purpose**. The MCP server never runs a firmware method on its own,
so an AI agent cannot flash a PLC. A person runs this tool during a maintenance window.
The tool does not start until someone commits an approval to Git.

---

## Quick start

The image is on Docker Hub as
[`wagoalex/wago-plc-mcp-server-fwupdate`](https://hub.docker.com/r/wagoalex/wago-plc-mcp-server-fwupdate).
It has the same version tags as the MCP server.
You need this folder for `docker-compose.yml` and `_env`. You do not need Python.

For a step-by-step procedure on a Windows or Linux laptop, see
[Update firmware from a Windows or Linux laptop](../docs/firmware-updates.md#update-firmware-from-a-windows-or-linux-laptop).
The commands below are the same in PowerShell and in a Linux shell.

```bash
git clone https://github.com/WagoAlex/wago-plc-mcp-server.git
cd wago-plc-mcp-server/fwupdate
cp _env .env
docker compose pull
```

Set these values in `.env`:

| Setting | Meaning |
|---|---|
| `PLC_IP`, `PLC_PASSWORD` | The device and its password |
| `FIRMWARE_SOURCE` | The location of your `.wup` bundles (directory, share, S3, HTTPS) |
| `POLICY_HOST_DIR` | Your checkout of the config repository, with `firmware-policy.yaml` |
| `FIRMWARE_HOST_DIR` | Only for the default source, a mounted directory |

Then do these steps in this order:

```bash
# 1. Rehearse. The tool uploads and checks the image, then cancels.
#    It never calls Start, so nothing is flashed.
docker compose run --rm -e DRY_RUN=true fwupdate

# 2. Update one device
docker compose run --rm fwupdate

# 3. Or update each device that your policy approves, one after the other
docker compose run --rm -e DRY_RUN=true fleet
docker compose run --rm fleet
```

If you changed the source code in this checkout, add `--build` to the `docker compose run` command.
Then Docker uses your local build instead of the published image.

A run takes about 5-15 minutes for each device. The upload and the reboot of the device take most of this time.

> **Stay with steps 2 and 3 until they are complete.** These steps write to the flash memory and restart a PLC.
> Run them in a visible window and watch the output.
> Do not run them in the background. Do not send their output to a process that can keep them alive after you want to stop.

---

## What can go wrong, and what the tool does

| Situation | What happens |
|---|---|
| The device has a firmware build below its minimum | Refused before the tool writes anything. See below |
| The device is not approved in Git | Refused before the tool connects to the device |
| Someone changed the approval but did not commit it | Refused. A policy that is not committed is not an authorization |
| The approval names a different revision than the bundle | Refused. The message shows both values |
| Two bundles match the device | Refused. The message lists both. The tool never guesses |
| The device already has that version | Refused, unless `FW_ALLOW_REFLASH=true` |
| The current version is outside the range of the bundle | Refused |
| The device refuses the image | The tool stops immediately and shows the `errorcause` of the device |
| The installation does not reach a state where it can finish | The tool stops at `POLL_TIMEOUT` and shows diagnostics |

The audit log records each of these results.

---

## Minimum firmware build

Some hardware cannot go directly from an old build to the new one. It needs an intermediate update first.
The bundles do not show this: all of them declare the same wide range, `3.0.0-4.9.99`.
So the tool does a separate check. It reads `0-0-version-softwarereleaseindex` (the `31` in `04.09.01(31)`)
and refuses before `Activate`:

```
==> Device identity: order=0750-8302  current firmware=04.09.01(31)
FATAL: 0750-8302 is at build 28, below the minimum 30 for this update path.
       Update it to build 30 first.
```

The check applies only to `.wup` bundles. It runs after the tool finds the bundle.
The CC100-IEC62443 uses a different build scheme (`02.00.13(04)`), so the tool does not do this check for its `.zip` bundles.

If the tool cannot read the build, it refuses. It does not assume that the build is correct.
The minimum build for each device class is a fact about the fleet, so it is in the config repository:
[Minimum firmware before an update](../docs/firmware-approvals.md#minimum-firmware-before-an-update).

## What the tool checks at run time

You write and review approvals **in your config repository**.
The config repository describes how to write an approval, the entry forms, and who approves it:
[Approve a firmware update](../docs/firmware-approvals.md).

This section describes what the container does with that file.
Before it flashes anything, it refuses unless all of these conditions are true:

1. Git **tracks** the policy file.
2. The file in the working tree is **the same as the committed file**. A local change authorizes nothing.
3. The policy lists the IP of the device with the **exact revision** that the bundle declares.
4. Optional (`FW_REQUIRE_SIGNED_COMMIT=true`): `HEAD` has a **valid signature**.
5. Optional (`FW_REQUIRE_SEPARATE_APPROVER=true`): the approver is not the proposer.

### What the tool installs when no revision is named

A policy entry lists the revisions that a device can run.
If there is no `TARGET_VERSION` and no revision in the ops file, the tool installs the **newest allowed** revision.
An entry can set a different `default`.
The tool refuses a revision that is not in the list, and it shows the allowed revisions:

```
FATAL: refused - 192.168.42.115 is approved for firmware 4.9.1, but the
       resolved bundle is 4.9.50.
```

The allowed revisions for a device are a decision about the fleet.
So the config repository, where you write approvals, describes the entry forms:
[Standing approval](../docs/firmware-approvals.md#standing-approval-the-fleet-policy).

### Nobody types their own name

You never type `approved_by` by hand. The tool takes the approver from the most authenticated source that it has:

| Priority | Source | Available when |
|---|---|---|
| 1 | **Pull request review** | CI read the review approvals of the pull request at the merge. CI sends them as `WAGO_APPROVED_BY`, with a reference in `WAGO_APPROVAL_REF` |
| 2 | Authenticated actor | Someone merged a pull request without a review approval, or pushed directly. CI sends only `WAGO_APPROVED_BY` |
| 3 | Commit author | You run the tool by hand, not in CI |
| 4 | The value in the file | None of the sources above is available. This is the weakest source: a typed name proves nothing |

The tool **allows and records** self-approval. It does not refuse it.
One engineer who maintains a rack does not need a second account:

```
==> NOTE: proposer and approver are the same person (self-approved).
    Allowed, and recorded as such in the audit log.
==> Authorized by commit 3968873334d8 (/policy/ops/fw-pfc300-119.yaml),
    signed off by A. Engineer <a@example.com> [commit author, self-approved]:
    192.168.42.119 -> 4.9.1
```

For a change-control requirement, set `FW_REQUIRE_SEPARATE_APPROVER=true`. Then the tool refuses self-approval.

There is a cost to the automatic approver. A file with an empty `approved_by` is no longer refused,
because the commit and the merge **are** the approval.
The branch-protection settings of your config repository decide if a second person must take part, not this tool.
The tool records what happened in both cases.
The config repository describes how to set this up, and who counts as the approver for each type of merge:
[Who counts as the approver](../docs/firmware-approvals.md#who-counts-as-the-approver).

After a successful check, the tool shows the authorizing commit. If the entry names a reviewer, it shows the reviewer too:

```
==> Authorized by commit 18d2cbfef290 (/policy/firmware-policy.yaml), signed off by ALEX: 192.168.42.119 -> 4.9.1
```

A refusal shows the reason. The tool stops before it connects to the device:

```
FATAL: refused - 192.168.42.115 is approved for firmware 4.9.1, but the resolved
bundle is 4.9.50. Commit a policy change if 4.9.50 is what you want.
```

Mount the checkout **with its `.git` directory**. The `.git` directory proves that someone committed the approval.
Set `FW_POLICY_FILE` to the policy file:

```env
# .env - this is a host path, so set it here, not with -e
POLICY_HOST_DIR=/path/to/wago-plc-config
```

`DRY_RUN=true` skips the Git check on purpose. A dry run never calls `Start`, so it cannot flash anything.
Rehearse first, then ask for the approval.
`FW_AUTHZ=off` disables the Git check fully. For when to use it and when not, see
[Running this securely](#running-this-securely).

## The audit chain records each run

A firmware flash is the action with the largest effect in the fleet.
So it writes to the **same tamper-evident hash chain** as the MCP server and `scripts/apply.py`.
It is not a separate log and not a copy of the code: the image uses `src/audit.py` from the server source,
and the `../data:/app/data` mount is the same volume.

The chain records each result, also the refusals.
After an incident, the important question is who tried and got a refusal:

| `result` | When |
|---|---|
| `authorized` | The Git check passed. The record has the commit SHA and `approved_by` |
| `refused: ...` | A check refused the run. The record has the exact reason |
| `ok` | The flash is complete. The record has the new firmware version |
| `failed: device reports Error` | The device refused the image. The record has the `errorcause` of the device |
| `failed: timed out ...` | The installation did not reach a state where it can finish |
| `aborted: ...` | The run stopped during the flash. An incident review needs this state most |
| `dry run ok (not flashed)` | A rehearsal. The record says that nothing was flashed |
| `proceeding without git authorization` | Someone used `FW_AUTHZ=off` |

```json
{"ts": "2026-09-07T12:45:37Z", "action": "firmware_update", "plc": "192.168.42.111",
 "agent": "fwupdate", "result": "refused: 192.168.42.111 is not listed in the firmware policy",
 "prev": "7c49824b5eca...", "revision": "4.9.1",
 "authorization_file": "/policy/firmware-policy.yaml"}
```

The record of an authorized run also shows who approved it, and how the tool found that:

```json
{"result": "authorized", "revision": "4.9.1", "commit": "3968873334d8...",
 "approved_by": "bob [PR review (WagoAlex/wago-plc-config#4 opened by alice, approved by bob, merged by bob)]",
 "self_approved": false,
 "approval_ref": "WagoAlex/wago-plc-config#4 opened by alice, approved by bob, merged by bob"}
```

For the commands that read and check the chain, see
[Verifying the trail afterwards](#verifying-the-trail-afterwards).

Passwords never go into the log. `audit.redact_details()` runs before the tool calculates the hash.
So the hash covers exactly the stored record, and you can check it.

## The whole fleet in one command

`fleet.py` reads the same policy and updates each approved device
**one after the other**. It starts one child process for each device:

```bash
docker compose run --rm -e DRY_RUN=true fleet   # rehearse the whole fleet
docker compose run --rm fleet                   # then do the update
```

The tool updates one device at a time on purpose.
Firmware updates have device-specific problems, for example the `/tmp/fwupdate` permission requirement
or the time to call `Finish` at `Unconfirmed`. It is much easier to find these problems one device at a time.
Many reboots at the same time also increase the effect of a problem that nobody found yet.
With one process for each device, a crash cannot affect the next device.
If a device fails, the tool reports it and continues with the next device.
The summary at the end lists each result. The exit code is not zero if a device failed.

The passwords for each device use the same convention as the MCP server:
a Docker secret at `/run/secrets/plc_password_<ip_with_underscores>`.
If there is no secret, the tool uses `PLC_PASSWORD` for the whole fleet.

## Where bundles come from - `FIRMWARE_SOURCE`

The later steps (catalog, upload, flash) always see a normal directory of `.wup` files.
So you can change the source:

| `FIRMWARE_SOURCE` | What it is |
|---|---|
| `/firmware` | A mounted directory. Set `FIRMWARE_HOST_DIR` and use the compose mount |
| `file:///mnt/fwshare` | A network share (SMB/NFS) that the **host** already mounted. The operating system mounts it, not this container |
| `s3://bucket/firmware/` | An S3 bucket, or an S3-compatible store with `AWS_ENDPOINT_URL` (MinIO, Ceph). Uses the standard AWS credential variables |
| `https://host/path/PFC-G2_update_V040901.wup` | One bundle over HTTPS. **A Teams, SharePoint, or OneDrive share link is this type**, after you add `?download=1` to an "anyone with the link" URL |
| `https://host/path/index.json` | A manifest. Use it to supply a full set of bundles for many devices over HTTPS, from any host that supplies static files |

The manifest format (`sha256` is optional, but the tool checks it when it is there):

```json
[
  {"name": "PFC-G2-Linux_update_V040901_31_r9d0900aaed.wup",
   "url":  "https://host/fw/PFC-G2-Linux_update_V040901_31_r9d0900aaed.wup",
   "sha256": "..."},
  {"name": "WP400-Linux_update_V040901_31_r9d0900aaed.wup",
   "url":  "https://host/fw/WP400-Linux_update_V040901_31_r9d0900aaed.wup"}
]
```

For a source that needs authentication (SharePoint with a token, Artifactory, a gateway for a private bucket),
set `FIRMWARE_SOURCE_TOKEN`. The tool sends it as `Authorization: Bearer`.

The `fwcache` volume keeps remote bundles by name and size, so a second run does not download files of about 200 MB again.
The tool writes each download to a `.part` file and renames it only after success.
So the tool never uses an interrupted download as a cached bundle.
If the `sha256` is wrong, the tool deletes the download and stops.
WAGO also signs each `.wup` file, and the device refuses a damaged or wrong image with `SignatureInvalid` or `SignatureTooOld`.
So these checks are an early and cheap protection, not the only one.

To see what a source supplies, without a connection to a device:

```bash
docker compose run --rm --entrypoint python fwupdate source.py s3://my-bucket/fw /tmp/cache
```

## Catalog mode (default) - the tool finds the hardware and the correct bundle

Set `FIRMWARE_HOST_DIR` to a directory with `.wup` bundles for any mix of hardware
(CC100, PFC100/200/300, Edge Controller/TP600, WP400). The container does these steps:

1. It reads the `Identity/OrderNumber` and the current firmware version of the device.
2. It makes a catalog from the `package-info.xml` of each bundle in the directory (`catalog.py` / `build_catalog.py`).
   It does not use the file names.
3. It selects the bundle whose `ArticleList` contains the order number of the device.
   If exactly one bundle matches, it uses that bundle. If more than one matches, the container **refuses and lists them**.
   It never guesses, for the reason in
   [why the revision must be exact](../docs/firmware-approvals.md#why-the-revision-must-be-exact).
   `TARGET_VERSION`, or the revision in the policy for a fleet run, selects one of them.
4. Before it changes anything, it checks that the current version of the device is in the upgrade or downgrade range that *this bundle* declares.
5. It refuses to run, and flashes nothing, in these cases: no bundle matches the order number,
   more than one bundle matches and there is no `TARGET_VERSION`, the device already has the target version,
   or the current version is outside the range of the bundle.

```bash
cp _env .env
# edit .env: PLC_IP, PLC_PASSWORD, FIRMWARE_HOST_DIR (a directory of .wup files)

docker compose run --rm fwupdate
```

This is real output from a live PFC300 that nobody had updated before.
The tool found the device and selected its bundle. Nobody read the XML by hand:
```
==> Device identity: order=0750-8302  current firmware=04.08.09
==> Building catalog from /firmware
    6 bundle(s) found
==> Resolved: PFC-300-Linux_update_V040901_31_r9d0900aaed.wup (upgrade 04.08.09 -> 4.9.1, build 31)
```

Set `TARGET_VERSION` to select one of several bundles, to go back to an older release,
or to keep a device at an older release while other devices get the new one.
It takes the exact revision string that a bundle declares.
To see the available revisions, run `build_catalog.py <dir>`:
```bash
docker compose run --rm -e TARGET_VERSION=4.9.1 fwupdate
```

## CC100-IEC62443 - `.zip` bundles

The CC100-IEC62443 (`751-9412`, firmware 02.x) does not use `.wup` files. Its firmware is a signed `.zip` file,
for example `wago-image-wago-cc100-02.00.13-fw-bundle.zip`.
It contains a `bundle-config.json` with the version and the supported order numbers.
Put it in the same firmware folder. The catalog reads both formats and ignores other `.zip` files.

For these devices, the tool uses the WDA `Update` feature, not `FirmwareUpdate`:

| Step | WDA call |
|---|---|
| 1. Make an update source | `0-0-update-createupdatefile` (`Name`) -> `UpdateFile` (file ID) + `Instance` |
| 2. Upload the full `.zip` file | `PATCH /files/{file_id}`, chunks of about 4 MB |
| 3a. Dry run: remove the source | `0-0-update-removesource` (`Source`) |
| 3b. Real run: start | `0-0-update-start` (`Source`, `ExpectStatusRequest=false`) |
| 4. Wait | Poll `0-0-update-status` (0 ReadyOrDone, 1 InProgress, 2 Error) through the reboot |

The differences from `.wup` bundles:

- The approval in `firmware-policy.yaml` uses the exact version string of the bundle: `192.168.2.85: { allowed: ["02.00.13"] }`.
- The bundle declares no upgrade or downgrade range. The device checks the signature and the compatibility. A refusal shows the reason, for example `InvalidSignature` or `UpdateIncompatible`.
- There is no minimum-build check (see above).

## Manual mode - skip the catalog

Set `WUP_PATH` to an exact file, with a path *in* the container under `/firmware/`.
Then the tool does not use the catalog. It uses exactly that bundle, and only the device checks the compatibility:
```bash
docker compose run --rm -e WUP_PATH=/firmware/WP400-Linux_update_V040901_31_r9d0900aaed.wup fwupdate
```

## What a run looks like

A dry run (`DRY_RUN=true`) selects the bundle, calls `Activate`, uploads all chunks, and lets the device check the image.
Then it cancels and clears the session. It never calls `Start`, the step that writes the flash memory.
Do a dry run on each device class that you did not update before.

A real run shows its progress live: `Activate` → upload chunks → `Start` → poll through the automatic reboot → `Finish` → `Clear`.
This is real output from a live run:

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

**The progress stays at about 93%.** It did not reach 100 on any tested device (a WP400 and two PFC200 G2).
The real completion signal is the status `Unconfirmed (4)`. The poll loop waits for this status before it calls `Finish`.

## When an update fails

The container stops when the status is `Error (7)` or `Revert (6)`. It does not wait for `POLL_TIMEOUT`.
It shows what the device reports:

```
FATAL: update failed - device reports Error (7)
    errorcause: SignatureTooOld (602)
    debuginfo: ...
    revertable: True
    Recent log:
    ...
```

`errorcause` is the useful field. The hundreds digit shows the phase that failed:
2xx signature, 3xx resources, 4xx backup, 6xx the RAUC installation, 900 self-test, 1000 confirmation timeout.
For the full table, see [`docs/wda-firmware-update.md`](../docs/wda-firmware-update.md).

## Environment variables

| Variable | Required | Default | Notes |
|---|---|---|---|
| `PLC_IP` | yes | - | IP of the device |
| `PLC_PASSWORD` | yes | - | |
| `PLC_USERNAME` | no | `admin` | |
| `FIRMWARE_SOURCE` | no | `/firmware` | The source of the bundles: a path, `file://`, `s3://`, or `https://` (see above) |
| `FIRMWARE_HOST_DIR` | yes for the default source, a mounted directory | - | **Host** directory of `.wup` files. The compose volume mount uses it |
| `FWUPDATE_VERSION` | no | `latest` | Image tag to pull, for example `2.4.0` to use one release |
| `FIRMWARE_CACHE` | no | `/firmware-cache` | The directory that receives the files of a remote source |
| `FIRMWARE_SOURCE_TOKEN` | no | not set | Bearer token for an HTTPS source that needs authentication |
| `POLICY_HOST_DIR` | yes, unless `FW_AUTHZ=off` | `.` | **Host** path of the Git checkout with the policy. The container mounts it at `/policy` |
| `FW_POLICY_FILE` | no | `/policy/firmware-policy.yaml` | The committed file with the approvals |
| `FW_AUTHZ` | no | `on` | `off` disables the Git check fully, with a clear warning |
| `FW_REQUIRE_SIGNED_COMMIT` | no | `false` | Also require a valid signature on `HEAD` |
| `FW_REQUIRE_SEPARATE_APPROVER` | no | `false` | Refuse self-approval. By default, the tool records it |
| `WAGO_APPROVED_BY` | no | automatic | The authenticated approver. CI sets it, the same as for `scripts/apply.py`. Without it, the tool uses the commit author |
| `TARGET_VERSION` | no | not set = only one bundle can match | The exact bundle revision, for example `4.9.1`. Necessary when more than one bundle in the directory lists the order number of the device |
| `WUP_PATH` | no | not set = catalog mode | Path in the container to an exact bundle. If set, the tool does not use the catalog |
| `CHUNK_SIZE` | no | `4000000` | Bytes for each chunk. About 4 MB is the tested safe maximum. A larger chunk exceeds a request-size limit in `lighttpd` |
| `POLL_INTERVAL` | no | `6` | Seconds between two status polls |
| `HTTP_TIMEOUT` | no | `45` | Seconds for each HTTP request. The CC100 needs 45 or more: with 30, it times out during the installation. This is a maximum, not a delay |
| `FW_ALLOW_REFLASH` | no | `false` | Install the version that the device already has (the tool still checks the range) |
| `AUDIT_LOG_FILE` | no | `/app/data/audit.log` | The shared tamper-evident chain. An empty value disables the audit records |
| `POLL_TIMEOUT` | no | `900` | Seconds to wait until the installation can finish (`status=Unconfirmed` or `progress=100`). Then the tool stops |

## Show the catalog without the container

```bash
python3 build_catalog.py <directory-with-bundles>
```
This command shows the revision, build index, article count, and upgrade and downgrade ranges of each bundle.
Use it to see the available `TARGET_VERSION` values before you start the container.

## Known preconditions on the device (the container does not fix them)

If `Activate` fails, the directory `/tmp/fwupdate` on the device probably does not exist, or has the wrong owner.
Correct it one time with SSH:
```bash
mkdir -p /tmp/fwupdate && chgrp admin /tmp/fwupdate && chmod 770 /tmp/fwupdate
```

The container needs `network_mode: host`, because it needs direct LAN access to the PLC subnet.

## Before your first production window

- [ ] Rehearse with `DRY_RUN=true` on each device class that you did not update before, not only on one -
      [What a run looks like](#what-a-run-looks-like)
- [ ] Make sure that `/tmp/fwupdate` exists on each device with the correct owner -
      [Known preconditions](#known-preconditions-on-the-device-the-container-does-not-fix-them)
- [ ] Expect a slow reboot. A CC100 needed 10 minutes to come back, a WP400 about one minute -
      [What a run looks like](#what-a-run-looks-like)
- [ ] Remember that the progress stays at about 93% and does not reach 100 -
      [What a run looks like](#what-a-run-looks-like)
- [ ] Decide between one device at a time and parallel updates, and write down why -
      [The whole fleet in one command](#the-whole-fleet-in-one-command)
- [ ] Review the credentials, the network placement, and the escape hatches -
      [Running this securely](#running-this-securely)
- [ ] Keep the failure table available -
      [When an update fails](#when-an-update-fails)

---

## Running this securely

A person runs this tool on a maintenance host, against a segmented OT network.
An auditor will ask about the points below.

**Credentials.** Use Docker secrets, not `.env`, when you can.
In fleet mode, the tool uses a secret for each device at `/run/secrets/plc_password_<ip_with_underscores>`.
If there is no secret, it uses `PLC_PASSWORD`.
The tool never writes passwords to the audit log: `audit.redact_details()` runs before the tool calculates the hash.
So the hash covers exactly the stored record, and you can check it.

**Network placement.** Run the tool on a host that has a route to the PLC subnets (`network_mode: host` is necessary).
The container needs no inbound access. It needs internet access only if `FIRMWARE_SOURCE` is a remote bundle store.

**Bundle integrity.** WAGO signs the `.wup` bundles. The device refuses a wrong or changed image (`SignatureInvalid`, `SignatureTooOld`).
An HTTPS manifest can also have a `sha256` for each bundle. The tool checks it before it puts the file in the cache.
The tool writes interrupted downloads to a `.part` file and never uses them as a complete bundle.

**Approval integrity.** In a regulated environment, set `FW_REQUIRE_SIGNED_COMMIT=true`.
Then `git verify-commit HEAD` must also pass.
Mount the policy checkout read-only (`:ro`). The tool only reads it.

**Separation of duties.** To make sure that a second person approves each firmware change,
use branch protection and required reviewers in your config repository.
Use the same settings as for your `ops/` files.
To also enforce it in this tool, set `FW_REQUIRE_SEPARATE_APPROVER=true`.

**Escape hatches, and when not to use them.** `FW_AUTHZ=off` disables the Git check.
`FW_ALLOW_REFLASH=true` allows the tool to install the version that the device already has.
Both show a notice, and the audit log records both.
Use `FW_AUTHZ=off` only for bench work on a device that is not part of a managed fleet.
A run with `FW_AUTHZ=off` is never an authorized run.

---

## Verifying the trail afterwards

```bash
# Did someone change the chain?
docker exec wmcp python /app/src/audit_verify.py --log /app/data/audit.log

# Show the firmware activity of this fleet
grep firmware_update data/audit.log | python3 -m json.tool

# Who approved a flash?
git -C /path/to/wago-plc-config show <commit-from-the-audit-record>
```
