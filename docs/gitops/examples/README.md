# GitOps examples - 20 use cases

Each file shows one use case. Copy the keys that you need into your own config repository.
For the setup and the daily workflow, see [GitOps setup](../../../README.md#gitops-setup) and [Use GitOps mode](../../../README.md#use-gitops-mode).

## Firmware generation: PTXdist only

All 20 files are for PTXdist PLCs: firmware 04.x, for example `04.09.01` (build 31).
Do not use them on a Yocto PLC, for example the CC100-IEC62443 with firmware `02.00.13`.
The two generations use different parameters for the same function:

| Function | PTXdist (these files) | Yocto |
|---|---|---|
| Time zone | `0-0-systemtime-timezone: 8` is CET | Instance `8` is Africa/El_Aaiun. Europe/Berlin is `247` |
| DNS servers | One flat `0-0-networking-dns-customdnsservers` | One list for each bridge: `0-0-networking-bridges-<N>-nameservers-dns` |

To identify the generation, read `0-0-version-firmwareversion`. For the other signals, see the "Device generations" section in [`wago-plc-skill/SKILL.md`](../../../wago-plc-skill/SKILL.md).
There are no Yocto examples yet, because we did not test them on a Yocto PLC.

## Test record

On 2026-09-18 we ran a dry run of each file with `apply.py` (without `--execute`) against two live PTXdist devices, firmware `04.09.01`:
a PFC300 (0750-8302) for files 01-13 and 16-20, and a TP600 (0762-5305) for files 14 and 15. For the test, we changed only the `plc_ip`.

- Files 01-15: the PLC returned each parameter in the file. Each file showed its drift, or "In sync".
- Files 16-18: `apply.py` showed the method call.
- Files 19-20: `apply.py` refused the method, because `approved_by` is empty. This is the correct result.

A dry run reads the PLC and changes nothing.

## How the list is divided

Each use case is in one group only.

1. **File type.** A use case either sets a state that must stay (`plcs/`), or runs an action one time (`ops/`).
2. **Area** (for `plcs/`). Each area is one group of WDA features. No parameter is in two files.
3. **Risk** (for `ops/`). `apply.py` refuses a dangerous method until a person approves it.

## Desired state - `plcs/`

CI compares each value in the file with the PLC and writes only the values that are different.
In your config repository, keep one file for each PLC (`plcs/<ip>.yaml`) and merge the keys of these examples into it.

| # | Area | Use case | Main parameters | Devices |
|---|---|---|---|---|
| 01 | Time | [NTP client](ptxdist/plcs/01-ntp-client.yaml) | `0-0-ntpclient-*` | All |
| 02 | Time | [Time zone](ptxdist/plcs/02-time-zone.yaml) | `0-0-systemtime-timezone` | All |
| 03 | Network identity | [Hostname and domain](ptxdist/plcs/03-hostname-domain.yaml) | `0-0-networking-hostname-customname`, `-domain-customdomain` | All |
| 04 | Network identity | [DNS servers](ptxdist/plcs/04-dns-servers.yaml) | `0-0-networking-dns-customdnsservers` | All |
| 05 | Monitoring | [SNMP](ptxdist/plcs/05-snmp.yaml) | `0-0-snmp-*` | All |
| 06 | Access security | [SSH without root login](ptxdist/plcs/06-ssh.yaml) | `0-0-ssh-*` | All |
| 07 | Access security | [FTPS only](ptxdist/plcs/07-file-transfer.yaml) | `0-0-ftp-enabled`, `0-0-ftps-enabled` | All |
| 08 | Access security | [Access token lifetime](ptxdist/plcs/08-token-lifetime.yaml) | `0-0-oauth2server-accesstokenlifetime` | All |
| 09 | Access security | [File integrity monitoring (AIDE)](ptxdist/plcs/09-integrity-monitoring.yaml) | `0-0-aide-enabled` | All |
| 10 | Runtime | [CODESYS 3 runtime](ptxdist/plcs/10-codesys-runtime.yaml) | `0-0-codesys3-enabled`, `-userauthentication-enabled` | Not WP400 |
| 11 | Runtime | [CODESYS WebVisu](ptxdist/plcs/11-codesys-webvisu.yaml) | `0-0-codesys3-webserver-*` | Not WP400 |
| 12 | Runtime | [Docker](ptxdist/plcs/12-docker.yaml) | `0-0-docker-enabled` | All |
| 13 | Fieldbus | [BACnet](ptxdist/plcs/13-bacnet.yaml) | `0-0-bacnet-general-enabled` | Not WP400 |
| 14 | HMI | [Display: brightness, night mode, screensaver](ptxdist/plcs/14-hmi-display.yaml) | `0-0-display-*` | TP600, WP400 |
| 15 | HMI | [Browser: reconnect, certificate check](ptxdist/plcs/15-hmi-browser.yaml) | `0-0-integratedwebbrowser-*` | TP600, WP400 |

## One-time actions - `ops/`

CI runs the method one time after the merge and then deletes the file.

| # | Risk | Use case | Method |
|---|---|---|---|
| 16 | Safe | [Synchronize the time now](ptxdist/ops/16-sync-time-now.yaml) | `0-0-ntpclient-updatetime` |
| 17 | Safe | [Run a file integrity check now](ptxdist/ops/17-integrity-check-now.yaml) | `0-0-aide-check` |
| 18 | Safe | [Log out all sessions](ptxdist/ops/18-revoke-all-tokens.yaml) | `0-0-oauth2server-revokealltokens` |
| 19 | Dangerous | [Restart the CODESYS runtime](ptxdist/ops/19-restart-codesys.yaml) | `0-0-codesys3-restart` |
| 20 | Dangerous | [Reboot the PLC](ptxdist/ops/20-reboot.yaml) | `0-0-reboot-beginreboot` |

For a dangerous method, the file has `requires_human: CRITICAL` and an empty `approved_by`.
With the CI workflow, the merge sets `approved_by` from the approving reviewer. Claude must never write a value in it.

## Not in this list

You cannot make these changes with the YAML files in this list:

| Change | Why | Use instead |
|---|---|---|
| Firmware update | It is a sequence of steps with a bundle upload, not one method call. The server proposes a firmware method only with `requires_human: CRITICAL` | An ops file with `action: firmware_update` and the firmware approval process in your config repository |
| Passwords and user accounts | A secret must not be in a Git repository | The WBM, or `0-0-localusers-*-changepassword` by hand |
| Certificates and VPN configuration files (OpenVPN, IPsec) | These are binary files, not short values | The WBM |
| Serial interface mode | `0-0-serialinterfaces-1-assignedmode` is read-only on some devices | The WBM |
| Web server protocol and TLS mode | The enum values are not documented here yet | Read them with `get_parameter` before you use them |

## Before you use an example

- Replace the IP addresses. They are the addresses of our test rack.
- Instance numbers (`communities-1`, `timezone` value `8`) can be different on your PLC. Read them first with `get_parameter`.
- Parameter IDs come from firmware build 31. Other builds can have different IDs.
- Run the dry run first: `python scripts/apply.py <file>`. Without `--execute`, it changes nothing.
