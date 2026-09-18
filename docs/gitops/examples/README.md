# GitOps examples - 20 use cases for each firmware generation

Each file shows one use case. Copy the keys that you need into your own config repository.
For the setup and the daily workflow, see [GitOps setup](../README.md#gitops-setup) and [Use GitOps mode](../README.md#use-gitops-mode).

## Select the set for your firmware generation

WAGO PLCs have two firmware generations. They use different parameters for the same function, so there is one set for each.
Do not use a file from one set on a PLC of the other generation.

| Set | Firmware | Example devices |
|---|---|---|
| [`ptxdist/`](#ptxdist-set) | 04.x, for example `04.09.01` (build 31) | CC100, PFC200 G2, PFC300, Edge Controller, WP400, TP600 |
| [`yocto/`](#yocto-set) | 02.x, for example `02.00.13` | CC100-IEC62443 (`0751-9412`) |

To identify the generation, read `0-0-version-firmwareversion`. For the other signals, see the "Device generations" section in [`wago-plc-skill/SKILL.md`](../../../wago-plc-skill/SKILL.md).

| Function | PTXdist | Yocto |
|---|---|---|
| Time zone | `0-0-systemtime-timezone: 8` is CET | Instance `8` is Africa/El_Aaiun. Europe/Berlin is `247` |
| DNS servers | One flat `0-0-networking-dns-customdnsservers` | One list for each bridge: `0-0-networking-bridges-<N>-nameservers-dns` |
| Services | SSH, FTP/FTPS, SNMP, Docker, CODESYS, BACnet, AIDE, HMI display and browser | None of these. Instead: remote syslog, NTP server, password rules, storm protection, MQTT broker, Portainer agent, I/O channel modes |
| `0-0-ntpclient-updatetime` | Runs at any time | Inactive while the NTP client is off |

## Test record

On 2026-09-18 we ran a dry run of each file with `apply.py` (without `--execute`) against live devices. A dry run reads the PLC and changes nothing.

| Set | Devices | Result |
|---|---|---|
| `ptxdist/` | PFC300 (0750-8302) for files 01-13 and 16-20, TP600 (0762-5305) for files 14 and 15, firmware `04.09.01`. For the test, we changed only the `plc_ip`. | 01-15: the PLC returned each parameter, and each file showed its drift or "In sync". 16-18: `apply.py` showed the method call. 19-20: refused, because `approved_by` is empty. This is the correct result. |
| `yocto/` | CC100-IEC62443 (0751-9412), firmware `02.00.13`, the device at `192.168.2.85` in the files | The same results for 01-20. |

## How the list is divided

Each use case is in one group only.

1. **File type.** A use case either sets a state that must stay (`plcs/`), or runs an action one time (`ops/`).
2. **Area** (for `plcs/`). Each area is one group of WDA features. No parameter is in two files.
3. **Risk** (for `ops/`). `apply.py` refuses a dangerous method until a person approves it.

## PTXdist set

### PTXdist - desired state (`ptxdist/plcs/`)

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

### PTXdist - one-time actions (`ptxdist/ops/`)

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

## Yocto set

All files use `192.168.2.85`, the CC100-IEC62443 in our test rack. Replace the IP address.

### Yocto - desired state (`yocto/plcs/`)

| # | Area | Use case | Main parameters |
|---|---|---|---|
| 01 | Time | [NTP client](yocto/plcs/01-ntp-client.yaml) | `0-0-ntpclient-enabled`, `-configuredtimeservers` |
| 02 | Time | [Time zone](yocto/plcs/02-time-zone.yaml) | `0-0-systemtime-timezone` (247 = Europe/Berlin) |
| 03 | Time | [NTP server on the PLC](yocto/plcs/03-ntp-server.yaml) | `0-0-ntpserver-*` |
| 04 | Network identity | [Hostname](yocto/plcs/04-hostname.yaml) | `0-0-networking-hostname-customname` |
| 05 | Network identity | [DNS servers of one bridge](yocto/plcs/05-dns-servers.yaml) | `0-0-networking-bridges-<N>-nameservers-dns` |
| 06 | Logging | [Remote syslog](yocto/plcs/06-remote-syslog.yaml) | `0-0-logging-rsyslog-clients-1-*` |
| 07 | Logging | [Minimum log level](yocto/plcs/07-log-level.yaml) | `0-0-logging-minloglevel` |
| 08 | Access security | [Access token lifetime](yocto/plcs/08-token-lifetime.yaml) | `0-0-oauth2server-accesstokenlifetime` |
| 09 | Access security | [Password rules](yocto/plcs/09-password-rules.yaml) | `0-0-accountmanagement-passwordquality-*` |
| 10 | Access security | [USB service interface off](yocto/plcs/10-usb-service-interface.yaml) | `0-0-usbserviceinterface-enabled` |
| 11 | Access security | [Physical controls off](yocto/plcs/11-physical-controls.yaml) | `0-0-physicalcontrols-disableall` |
| 12 | Network protection | [Multicast storm protection](yocto/plcs/12-storm-protection.yaml) | `0-0-networking-stormprotection-multicastprotection-enabled` |
| 13 | Runtime | [Local MQTT broker off](yocto/plcs/13-mqtt-broker.yaml) | `0-0-mqttbroker-enabled` |
| 14 | Runtime | [Portainer Edge agent: trusted certificates only](yocto/plcs/14-portainer-agent.yaml) | `0-0-portainer-edgeagent-allowselfsignedcertificates` |
| 15 | I/O | [Analog input mode](yocto/plcs/15-analog-input-mode.yaml) | `0-0-io-channels-<N>-measurementmode` |

### Yocto - one-time actions (`yocto/ops/`)

| # | Risk | Use case | Method |
|---|---|---|---|
| 16 | Safe | [Synchronize the time now](yocto/ops/16-sync-time-now.yaml) | `0-0-ntpclient-updatetime` (needs file 01 first) |
| 17 | Safe | [Calculate the configuration checksum](yocto/ops/17-config-checksum.yaml) | `0-0-security-calculateconfigchecksum` |
| 18 | Safe | [Log out all sessions](yocto/ops/18-revoke-all-tokens.yaml) | `0-0-oauth2server-revokealltokens` |
| 19 | Dangerous | [Reboot the PLC](yocto/ops/19-reboot.yaml) | `0-0-reboot-beginreboot` |
| 20 | Dangerous | [Reset to factory settings](yocto/ops/20-factory-reset.yaml) | `0-0-factorysettings-reset` |

These parameters are not in the Yocto set on purpose:

- Direct output values (`0-0-io-channels-<N>-dovalue`, `-aovalue`). They switch physical outputs.
- The IP and port settings of the bridges. A wrong value disconnects the PLC.
- The rule lists for firewall, MQTT access, and routing. These are complex lists that need their own review.

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
- Use the set for the firmware generation of your PLC.
- Instance numbers (`communities-1`, `timezone` value `8`) can be different on your PLC. Read them first with `get_parameter`.
- The PTXdist IDs come from firmware build 31, the Yocto IDs from firmware 02.00.13. Other versions can have different IDs.
- Run the dry run first: `python scripts/apply.py <file>`. Without `--execute`, it changes nothing.
