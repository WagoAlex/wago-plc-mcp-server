# Approve a firmware update

This page describes how to approve a firmware update in your GitOps config repository.
The `fwupdate` tool flashes a device only after this approval.
For the tool itself, see [`fwupdate/README.md`](../fwupdate/README.md). For the setup of the config repository, see [GitOps setup](gitops/README.md#gitops-setup).

You cannot undo a firmware update with a new pull request.
For this reason, the approval is in a Git repository and not on a command line.
The updater flashes a device only if the authorization file:

- is a tracked file in Git,
- has no uncommitted changes, and
- names the exact revision of the selected bundle.

A local change does not authorize anything.

## Three ways to start a firmware update

| Route | Approval | Who runs it | Use it when |
|---|---|---|---|
| `ops/fw-*.yaml` | The pull request that merges it | CI, at the merge | For routine work. It leaves a pull request and a file that others can review. |
| **Run workflow** | The standing approval in `firmware-policy.yaml` | CI, when you click it | You have a standing approval and want to apply it now |
| Updater run by hand | The standing approval in `firmware-policy.yaml` | You, on a computer in the plant network | No runner is available, or you want a dry run outside CI |

All three routes record the approver. You do not type a name into a file.

For the first route, the config repository needs the `apply.yml` workflow: copy [`gitops/apply.yml`](gitops/apply.yml).
For the second route, it also needs the `firmware.yml` workflow: copy [`gitops/firmware.yml`](gitops/firmware.yml).
Put both in `.github/workflows/` of your config repository.

## One-time approval: firmware as an ops file

```yaml
# ops/fw-pfc300-119.yaml
id: fw-pfc300-119
proposed_at: 2026-09-07T13:00:00+00:00
proposed_by: engineer
plc_ip: 192.168.42.119
action: firmware_update
target_version: "4.9.1"      # exact bundle revision
requires_human: CRITICAL
approved_by: ""              # CI takes it from the pull request review at the merge
```

When you merge this file, CI **flashes the device** and then deletes the file.
If the update fails, the file stays, so you can try again.

The ops file is the authorization. It applies to one device and one revision.
You cannot use a merged file for a different device.
Keep templates with the extension `.example.yaml`. CI never runs `.example.yaml` files.

If the device already runs the target version, add `allow_reflash: true`.
Without this setting, the updater refuses to write the version that a device already has.

> [!WARNING]
> **Merge ops files one at a time.** CI applies all files of a merge in the same run.
> If you merge the files for many devices together, all of them restart at the same time.
> It is also more difficult to find the device that stopped when several devices are down.

## Standing approval: the fleet policy

`firmware-policy.yaml` holds approvals for more than one run.
A merge of this file does not start an update.
An engineer applies it later, with the updater during a maintenance window or with **Actions → Firmware update → Run workflow**.

An entry lists the revisions that a device can run:

```yaml
approvals:
  # One permitted revision.
  192.168.42.110: { allowed: ["4.9.1"] }

  # Several permitted. The newest is the default: what a fleet run or a
  # Run workflow installs when no revision is named.
  192.168.42.121: { allowed: ["4.8.9", "4.9.1"] }

  # Permitted to go newer, held at 4.9.1 on purpose.
  192.168.42.116:
    allowed: ["4.9.1", "4.9.50"]
    default: "4.9.1"
```

- A short entry, for example `192.168.42.110: "4.9.1"`, also works. It permits one revision.
- The updater refuses a `default:` that is not in the `allowed` list.
- An older revision in the list permits a downgrade. It does not become the default, because the newest allowed revision stays the default.

## Which bundle each device class takes

| Device class | Bundle | Revision (September 2026) |
|---|---|---|
| CC100 | `CC100-Linux` | 4.9.1 |
| PFC200 G2, **except** `0750-8217` | `PFC-G2-Linux` | 4.9.1 |
| PFC200 G2 `0750-8217` (modem) | `PFC-G2-Linux-red-autoupdate` | **4.9.50** (includes the modem firmware) |
| PFC300 | `PFC-300-Linux` | 4.9.1 |
| TP600 and Edge Controller | `TP-Linux` | 4.9.1 |
| WP400 | `WP400-Linux` | 4.9.1 |
| CC100-IEC62443 (Yocto) | `wago-image-wago-cc100-<version>-fw-bundle.zip` | 02.00.13 |

WAGO releases new firmware up to three times a year.
After each release, check this table and the approved revisions in `firmware-policy.yaml`.

## Minimum firmware before an update

Some hardware must be at a minimum build before it can take an update.
Below that build, the device needs an intermediate update first.
The bundles do not show this limit, because all `.wup` bundles declare the same range `3.0.0-4.9.99`.
The updater reads `0-0-version-softwarereleaseindex` and refuses the update before it writes anything.

| Device class | Minimum build |
|---|---|
| PFC300 | **30** |
| CC100, PFC200 G2, TP600, Edge Controller | 28 |
| CC100-IEC62443 (Yocto, `.zip` bundles) | Not checked. This line numbers its builds differently: `02.00.13(04)`. |

## Pitfalls

- **You cannot identify `0750-8217` from the bundle metadata.**
  Both PFC-G2 bundles list the same 35 article numbers, including `0750-8217`.
  The red-autoupdate bundle has the higher revision.
  "Install the latest" would put the modem firmware on every other PFC200 G2.
  The approved revision in `firmware-policy.yaml` decides.
  If two bundles match, the updater refuses and does not guess.
- **Edge Controllers take the `TP-Linux` bundle.**
  They do not take the `0752-9xxx` Edge image, although its file name looks closer.
  The article list inside the bundle confirms this.
- **Yocto devices use a different firmware line.**
  The CC100-IEC62443 (`0751-9412`) takes a signed `.zip`, not a `.wup`.
  Its revision keeps the leading zeros: approve `"02.00.13"`, not `"2.0.13"`.

## Why the revision must be exact

The approved revision also selects the bundle.
The PFC200 G2 order number `0750-8212` is in the article list of two bundles:

- the standard `4.9.1` bundle, and
- the `red-autoupdate` `4.9.50` bundle. This is the `0750-8217` modem line with the modem firmware.

The two article lists are identical.
"The latest version wins" would put the modem firmware on every other PFC200 G2.
The revision in your config repository decides instead. See [Which bundle each device class takes](#which-bundle-each-device-class-takes).

## Yocto devices (CC100-IEC62443)

Yocto devices, for example the CC100-IEC62443 (`0751-9412`), use the same three routes and the same approval rules.
These items are different from the `.wup` devices:

| | `.wup` devices (PTXdist firmware) | CC100-IEC62443 (Yocto firmware) |
|---|---|---|
| Bundle | `CC100-Linux_update_V040901_31_*.wup` | `wago-image-wago-cc100-02.00.13-fw-bundle.zip` (signed, with `bundle-config.json`) |
| Revision to approve | `"4.9.1"` | `"02.00.13"`, exactly as the bundle declares it |
| WDA feature that the updater uses | `FirmwareUpdate` | `Update` (`update-createupdatefile`, `update-start`) |
| Minimum-build check | Yes (28 or 30) | No |
| Duration | 5 to 15 minutes | About 20 minutes (secure update on the ARM CPU) |

Standing approval in `firmware-policy.yaml`:

```yaml
approvals:
  192.168.2.85: { allowed: ["02.00.13"] }
```

One-time ops file:

```yaml
# ops/fw-cc100iec-85.yaml
id: fw-cc100iec-85
proposed_at: 2026-09-16T15:00:00+00:00
proposed_by: engineer
plc_ip: 192.168.2.85
action: firmware_update
target_version: "02.00.13"   # exact bundle version, leading zeros included
requires_human: CRITICAL
approved_by: ""              # CI takes it from the pull request review at the merge
allow_reflash: true          # only if the device already runs 02.00.13
```

Put the `.zip` file in the same `FIRMWARE_SOURCE` as the `.wup` bundles.
The updater reads both formats. It selects the bundle whose `supported-devices` list contains the order number of the device.

The MCP server blocks all `0-0-update-*` methods.
An agent cannot start this update, the same as a `FirmwareUpdate` update.

> [!NOTE]
> **Check the password first.** CI uses the one `PLC_PASSWORD` secret for every device.
> If a device has a different password, the CI login to this device fails.

## The review flow

```bash
git switch -c fw/approve-pfc300-119
# edit firmware-policy.yaml, or copy an ops/fw-*.example.yaml template
git commit -am "feat: approve FW 4.9.1 for PFC300 .119"
gh pr create --fill
```

The reviewer checks these three items and approves the pull request:

1. The revision matches a bundle that the fleet has.
2. The device is the correct device. An ops file applies to one IP address.
3. `allow_reflash` is set only if the device already runs that version.

The merge is the approval. You do **not** type a name into the file.
CI takes the approver from the pull request.

## Who counts as the approver

The **pull request** is the approval, not the commit.
The commit author is usually the person who proposed the change.
GitHub is the author of a squash or merge commit.
When you merge, CI reads the review approvals of the pull request and records them.

There are three possible results. The workflow allows all three, and the record shows which one occurred:

| What occurred | What CI records |
|---|---|
| A reviewer approved the pull request | The reviewers, the pull request number, the author, and the person who merged |
| A person merged the pull request without a review approval | The person who merged, and `no review approval` |
| Direct push to `main` | `direct push by <user> (no pull request)` |

The workflow allows self-approval: the same person proposes and merges.
One engineer who maintains a rack does not need a second account.
The record shows `self_approved: true`, so a later review can see that only one person made the change.

**The settings of your config repository decide if two people must approve.**
The tools record what occurred, but they cannot require a second person.
To require a second person, go to **Settings → Branches → Branch protection rules** and enable branch protection on `main`:

1. Select *Require a pull request before merging*.
2. Set *Require approvals* to 1.

For how the updater finds and checks the approver, the refusal messages, and `FW_REQUIRE_SEPARATE_APPROVER`, see
[fwupdate → Nobody types their own name](../fwupdate/README.md#nobody-types-their-own-name).

## Repository variables to set first

Set both variables in **Settings → Secrets and variables → Actions → Variables** of your config repository:

| Variable | Purpose |
|---|---|
| `FIRMWARE_SOURCE` | Where the runner finds the firmware bundles. For the permitted formats, see [fwupdate → Where bundles come from](../fwupdate/README.md#where-bundles-come-from---firmware_source). |
| `AUDIT_SYSLOG` | For example `udp://10.0.0.5:514`. The CI runner has no persistent storage for the audit log. Without this variable, an operation that CI runs leaves **no audit record**. |

For the content of the audit record and how to verify it, see [Firmware updates](firmware-updates.md).

## Troubleshooting

| Message | Cause | Action |
|---|---|---|
| `refused - <ip> is not listed in the firmware policy` | The device has no entry in `firmware-policy.yaml` | Open a pull request that adds the entry |
| `refused - <ip> is approved for firmware X, but the resolved bundle is Y` | The policy and the bundle do not agree. The container uses the wrong bundle folder, or the approval is old. | Change the policy in a pull request. Do not pass a different target on the command line. |
| `refused - firmware-policy.yaml has uncommitted changes` | You changed the file and did not commit it. On Windows, Git can also write CRLF line endings. | Commit the change. Add a `.gitattributes` file with `*.yaml text eol=lf` to keep YAML files at LF. |
| `REFUSED: ... dangerous method with no approved_by` | `apply.py` ran without an approver, for example by hand without `WAGO_APPROVED_BY`. CI always sets it. | Run the operation through a pull request, or set `WAGO_APPROVED_BY` |
