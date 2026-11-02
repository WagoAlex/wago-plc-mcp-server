# What do you need to update WAGO PLC firmware? {#plc-firmware-update}

The WAGO PLC MCP server **cannot flash a PLC**. A person or CI runs the separate `fwupdate` tool, and that tool needs a **committed Git approval** for the device and the firmware revision.

- `invoke_method` refuses all `firmware*` and `0-0-update-*` methods, so an agent cannot start an update.[](source:safety)
- `upload_file` sends the full file with one `PUT`, and the WDA docs record `413` for that call. Firmware uploads need chunks of about 4 MB.[](source:client)[](source:wda)
- In GitOps mode, the agent only proposes the change. A person reviews and merges the proposal.[](source:main)

@answer scope="Server 2.4.4, firmware 4.9.1 and 02.00.13. Checked in code and docs. No device touched. The upload limit was not tested through the MCP server."
@meta locale=en
@source safety title="Method safety gate (src/safety.py)" url=https://github.com/WagoAlex/wago-plc-mcp-server/blob/015769b42dc1de63020b95f9db0580cf21f6a2bf/src/safety.py#L22-L37
@source main title="invoke_method gates (src/main.py)" url=https://github.com/WagoAlex/wago-plc-mcp-server/blob/015769b42dc1de63020b95f9db0580cf21f6a2bf/src/main.py#L598-L615
@source client title="WDA client upload_file (src/wda_client.py)" url=https://github.com/WagoAlex/wago-plc-mcp-server/blob/015769b42dc1de63020b95f9db0580cf21f6a2bf/src/wda_client.py#L378-L386
@source activate title="Activate call in fwupdate (fwupdate/fw_update.py)" url=https://github.com/WagoAlex/wago-plc-mcp-server/blob/015769b42dc1de63020b95f9db0580cf21f6a2bf/fwupdate/fw_update.py#L379-L385
@source wda title="WDA firmware update reference" url=https://github.com/WagoAlex/wago-plc-mcp-server/blob/main/docs/wda-firmware-update.md
@source guide title="Firmware updates" url=https://github.com/WagoAlex/wago-plc-mcp-server/blob/main/docs/firmware-updates.md
@source approvals title="Approve a firmware update" url=https://github.com/WagoAlex/wago-plc-mcp-server/blob/main/docs/firmware-approvals.md
@source readme title="fwupdate tool README" url=https://github.com/WagoAlex/wago-plc-mcp-server/blob/main/fwupdate/README.md

## Who can write firmware to a PLC? {#who-can-flash}

@architecture id=firmware-access title="Two separate paths to the PLC"
| agent | AI agent | external |
| engineer | Engineer or CI | external |
| files | Firmware files | database |
| mcp | MCP server | backend |
| policy | Approval repository | security |
| tool | fwupdate tool | backend |
| plc | WAGO PLC | cloud |
| audit | Audit log | database |
| agent > mcp | reads, proposes | dashed |
| engineer > policy | commits | security |
| policy > tool | checked | security |
| files > tool | selected | |
| mcp > plc | no firmware | dashed |
| tool > plc | flashes | emphasis |
| mcp > audit | records | |
| tool > audit | records | |

Both paths write to the same hash-chained audit log. The log also records each refusal.[](source:guide)

## What must be ready before you start? {#requirements}

| Item | Requirement |
| --- | --- |
| Host | Docker with Compose, and Git. Windows 10 or 11 and Linux both work. |
| Network | HTTPS (port 443) from the host to each PLC. The container uses `network_mode: host`. |
| Tool | The image `wagoalex/wago-plc-mcp-server-fwupdate` and the `fwupdate/` folder of the repository. |
| Firmware | The files from WAGO: `.wup`, or a signed `.zip` for the CC100-IEC62443. |
| Approval | A committed `firmware-policy.yaml` that names the device IP and the exact revision. |
| Credentials | The WBM user name and password. Use one Docker secret for each device if the passwords differ. |
| Device folder | `/tmp/fwupdate` on the PLC, with group `admin` and mode `0770`. |
| Minimum build | PFC300: 30. CC100, PFC200 G2, TP600, and Edge Controller: 28. The CC100-IEC62443 has no check. |
| Maintenance window | A stopped machine or process, because the PLC restarts during the update. |

## Which firmware file does each device take? {#firmware-files}

| Device | Firmware file | Revision to approve |
| --- | --- | --- |
| CC100 | `CC100-Linux` | `4.9.1` |
| PFC200 G2, except `0750-8217` | `PFC-G2-Linux` | `4.9.1` |
| PFC200 G2 `0750-8217` (modem) | `PFC-G2-Linux-red-autoupdate` | `4.9.50` {caution:Modem only} |
| PFC300 | `PFC-300-Linux` | `4.9.1` |
| TP600 and Edge Controller | `TP-Linux` | `4.9.1` |
| WP400 | `WP400-Linux` | `4.9.1` |
| CC100-IEC62443 | `wago-image-wago-cc100-02.00.13-fw-bundle.zip` | `02.00.13` {caution:Keep zeros} |

Both PFC-G2 files list the same article numbers, so the file data cannot identify `0750-8217`. The approved revision selects the file.[](source:approvals)

## How do you run an update? {#run-update}

@workflow id=update-flow title="From firmware file to updated PLC"
| get-files | Get firmware files | external |
| set-env | Set connection values | backend |
| commit | Commit approval | security |
| dry-run | Do a dry run | backend |
| flash | Flash the PLC | backend |
| verify | Verify audit log | database |
| get-files > set-env | |
| set-env > commit | |
| commit > dry-run | |
| dry-run > flash | passed | emphasis |
| flash > verify | done |

@steps id=update-steps
| s-files | Get firmware files | Copy the `.wup` or `.zip` files into the `firmware` folder. | update-flow | get-files |
| s-env | Set connection values | Copy `_env` to `.env`. Set `PLC_IP` and `PLC_PASSWORD`. | update-flow | set-env |
| s-commit | Commit approval | Add the IP and the revision to `firmware-policy.yaml`. Commit the file. | update-flow | commit |
| s-dry | Do a dry run | Run the tool with `DRY_RUN=true`. The tool uploads and checks the file, then cancels. | update-flow | dry-run |
| s-flash | Flash the PLC | Stop the machine. Run the tool. Wait for `==> Done.` | update-flow | flash |
| s-verify | Verify audit log | Run `audit_verify.py`. The result must show an intact chain. | update-flow | verify |

```yaml title="firmware-policy.yaml"
approvals:
  192.168.1.10: "4.9.1"
```

```bash title="Commands, in the fwupdate folder"
cp _env .env
docker compose pull
docker compose run --rm -e DRY_RUN=true fwupdate
docker compose run --rm fwupdate
```

To update all approved PLCs, replace `fwupdate` with `fleet` in the last two commands. The tool then updates one PLC after the other.[](source:readme)

## Which route should you use? {#routes}

| Route | Approval | Who runs it | Use it when |
| --- | --- | --- | --- |
| Tool by hand | Entry in `firmware-policy.yaml` | You, on a host in the plant network | No runner is available |
| `ops/fw-*.yaml` file | The merged pull request | CI, at the merge | For routine work {good:Best record} |
| **Run workflow** | Entry in `firmware-policy.yaml` | CI, when you click it | The approval exists and you want to use it now |

The CI routes need a self-hosted runner and the `apply.yml` and `firmware.yml` workflows. They also need the `FIRMWARE_SOURCE` and `AUDIT_SYSLOG` variables. Without `AUDIT_SYSLOG`, a CI run leaves no audit record.[](source:approvals)

@callout level=warning title="Merge ops files one at a time"
CI applies all files of a merge in the same run. If you merge many files together, all of those PLCs restart at the same time.

## What should you expect during the flash? {#during-flash}

@facts
| Duration | 5 to 15 minutes for each PLC. About 20 minutes on the CC100-IEC62443. |
| CC100 restart | Up to 10 minutes. |
| Progress | It stops at about 93%. The status `Unconfirmed (4)` is the real signal. |
| Last line | `==> Done.` with the status and the new firmware version. |

@callout level=warning title="Do not stop the tool during the flash"
Connect the host to mains power. Set the host to not sleep.
Do not press Ctrl+C. Do not close the window until the tool shows `==> Done.`
Do not run the tool in the background.

## What stops an update? {#refusals}

| Message | Action |
| --- | --- |
| `has uncommitted changes` | Commit the file. On Windows, also add `.gitattributes` with `*.yaml text eol=lf`. |
| `not listed in the firmware policy` | Add the device in a pull request. |
| `is approved for firmware X, but the resolved bundle is Y` | Correct the policy, or the firmware folder. |
| `bundles match order number` | Set `TARGET_VERSION` to the exact revision. |
| `Device is already at` | No action is necessary. Set `FW_ALLOW_REFLASH=true` only for an intentional reflash. |
| `below the minimum` | First update to the intermediate build in the message. |
| `activate failed` | Make `/tmp/fwupdate` on the PLC. Use the command below. |

```bash title="Run on the PLC with SSH"
mkdir -p /tmp/fwupdate && chgrp admin /tmp/fwupdate && chmod 770 /tmp/fwupdate
```

## What do the docs not answer yet? {#open-points}

@callout level=open-question title="Does the PLC application survive the update?"
The tool always sends `KeepCustomerApplication: false`.[](source:activate) No document states the effect on a CODESYS boot project.
Back up the application before an update. Test the result on a bench PLC before production.

@callout level=note title="SSH is missing from the laptop requirements"
The laptop procedure does not list SSH access.[](source:guide) The `/tmp/fwupdate` correction needs SSH.

@callout level=note title="The Edge Computer is a separate case"
The tested devices do not include the Edge Computer `0752-9xxx`.[](source:readme) It has a separate repository, `edge-computer-fw-update`. The Edge Controller does use this tool.

## Are you ready to update? {#checklist}

- [ ] The firmware file for each device is in the firmware folder.
- [ ] The approval is committed, and `firmware-policy.yaml` has no local changes.
- [ ] Each PLC is at or above its minimum build.
- [ ] You have a backup of the PLC application.
- [ ] The dry run shows `Start was never called` for each device class.
- [ ] The machine is stopped, and the host has mains power.
- [ ] You can stay with the tool until it shows `==> Done.`
