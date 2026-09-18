# GitOps YAML reference

This page describes the files in a GitOps config repository, for example `wago-plc-config`.
`apply.py` reads these files and compares the live PLC with them.
For the setup and the daily workflow, see the [GitOps guide](README.md).

> [!IMPORTANT]
> The parameter IDs on this page are for PTXdist PLCs (firmware 04.x, build 31).
> A Yocto PLC, for example the CC100-IEC62443, uses different IDs for some functions.
> Read the "Device generations" section in [`wago-plc-skill/SKILL.md`](../../wago-plc-skill/SKILL.md) before you use them.

## Repository layout

```
wago-plc-config/
├── plcs/
│   ├── 192.168.42.110.yaml   # one file for each PLC - the desired state
│   ├── 192.168.42.118.yaml
│   └── ...
└── ops/
    └── a3f1c2d8.yaml         # one-time actions (CI deletes the file after a successful run)
```

---

## Desired-state files - `plcs/<ip>.yaml`

This file sets the values that the PLC **must always have**.
`apply.py` reads the live values, compares them with this file, and writes only the values that are different.

```yaml
plc_ip: 192.168.42.118        # required - use the same IP as in the file name
managed_parameters:            # required - map of WDA parameter ID → desired value
  0-0-ntpclient-enabled: true
  0-0-ntpclient-configuredtimeservers:
    - 192.168.42.2
  0-0-snmp-enable: false
```

### Rules

- Use the same IP in `plc_ip` and in the file name. `apply.py` uses `plc_ip` and does not read the file name.
- `apply.py` compares values without case: `true`, `True`, and `"true"` are equal.
- `apply.py` converts each value to the type of the live value before it writes it. For example, YAML `"true"` becomes the boolean `true`, and YAML `"300"` becomes the integer `300` if the live value is an integer.
- Do not put a read-only parameter in the file, for example `0-0-version-firmwareversion`.
- Write a parameter with an array value, for example the NTP servers, as a YAML list.
- `apply.py` does not change a parameter that is not in the file.

---

## Ops files - `ops/<id>.yaml`

An ops file runs one action one time, for example a time sync or a reboot.
After a successful run with `--execute`, `apply.py` **deletes the file**.
If the method fails, `apply.py` keeps the file. Then the operator can examine the problem.

```yaml
id: a3f1c2d8                           # 8 hex characters, unique for each operation
proposed_at: 2026-06-21T14:22:00+00:00
proposed_by: agent-claude-code          # who proposed this action
plc_ip: 192.168.42.118
action: invoke_method                   # invoke_method, or firmware_update for the firmware process
method_id: 0-0-ntpclient-updatetime    # WDA method ID
arguments: {}                           # map of inArg name → value. Use {} for a method without arguments
```

---

## Parameters for each function

The tables show the WDA parameters that the `gitops.py` helper functions use.
All IDs start with `0-0-`. Some IDs contain an instance number, for example `communities-1`.
Some instances exist only after someone configures them, for example SNMP communities. Read an instance with `get_parameter` before you write it.

For 20 tested example files, see [`examples/`](examples/README.md).

### Cloud connection

The function `gitops.cloud_params()` makes these values.

| Parameter | Type | Notes |
|-----------|------|-------|
| `0-0-cloudconnections-1-transport-host` | string | MQTT broker host name or IP |
| `0-0-cloudconnections-1-cloudtype` | enum int | 2 = Any Cloud (generic MQTT) |
| `0-0-cloudconnections-1-identification-clientid` | string | Unique for each device |
| `0-0-cloudconnections-1-messaging-messagingprotocol` | enum int | 4 = Native MQTT |
| `0-0-cloudconnections-1-enabled` | bool | Write it together with `cloudtype` and `transport-host` |

> [!CAUTION]
> Put `cloudtype` and `transport-host` in the same write.
> If they do not agree, WDA returns error code 41. An example is an Azure IoT Hub host with `cloudtype: 2`.

```yaml
plc_ip: 192.168.42.117
managed_parameters:
  0-0-cloudconnections-1-transport-host: 192.168.42.2
  0-0-cloudconnections-1-cloudtype: 2
  0-0-cloudconnections-1-identification-clientid: PFC-117
  0-0-cloudconnections-1-messaging-messagingprotocol: 4
  0-0-cloudconnections-1-enabled: true
```

### NTP time sync

The function `gitops.ntp_params()` makes these values. All device classes have them.

| Parameter | Type | Notes |
|-----------|------|-------|
| `0-0-ntpclient-enabled` | bool | |
| `0-0-ntpclient-configuredtimeservers` | string[] | List of NTP server IPs or host names, in order |
| `0-0-ntpclient-updateinterval` | uint16 | Seconds between two syncs. The default is 600 |
| `0-0-ntpclient-isrunning` | bool | Read-only. Do not put it in a desired-state file |
| `0-0-ntpclient-istimeserveravailable` | bool | Read-only |

```yaml
plc_ip: 192.168.42.113
managed_parameters:
  0-0-ntpclient-enabled: true
  0-0-ntpclient-configuredtimeservers:
    - 192.168.42.2
    - 0.pool.ntp.org
  0-0-ntpclient-updateinterval: 300
```

Ops file for a time sync:

```yaml
id: b7d3e1f9
proposed_at: 2026-06-21T10:00:00+00:00
proposed_by: agent-claude-code
plc_ip: 192.168.42.113
action: invoke_method
method_id: 0-0-ntpclient-updatetime
arguments: {}
```

### SNMP

The function `gitops.snmp_params()` makes these values. All device classes have the general SNMP parameters.
The `communities-1-*` parameters exist only after the first community is configured.

| Parameter | Type | Notes |
|-----------|------|-------|
| `0-0-snmp-enable` | bool | |
| `0-0-snmp-communities-1-name` | string | Community string for v1/v2c |
| `0-0-snmp-communities-1-access` | enum int | 1 = read-only (default) |
| `0-0-snmp-location` | string | sysLocation value |
| `0-0-snmp-contact` | string | sysContact value |
| `0-0-snmp-name` | string | sysName value (read-only) |
| `0-0-snmp-description` | string | sysDescr value (read-only) |
| `0-0-snmp-objectid` | string | sysObjectID value (read-only) |
| `0-0-snmp-trapreceiversv1v2c` | instantiations | List of trap targets. Configure it in the WBM |
| `0-0-snmp-trapreceiversv3` | instantiations | List of SNMPv3 trap targets. Configure it in the WBM |

```yaml
plc_ip: 192.168.42.114
managed_parameters:
  0-0-snmp-enable: true
  0-0-snmp-communities-1-name: wago-lab
  0-0-snmp-location: Lab-Rack-42
  0-0-snmp-contact: admin@wago-lab.local
```

### Serial interface

The function `gitops.serial_params()` makes these values.
PFC200, PFC300, Edge Controller, and TP600 have them if the hardware variant has an RS-232/485 port.
The CC100 and the WP400 do not have them. On the PFC200, the port name is `X3`.

> [!WARNING]
> `0-0-serialinterfaces-1-assignedmode` is read-only on the PFC300.
> Check it with `get_parameter_definition` before you put it in a file.

| Parameter | Type | Notes |
|-----------|------|-------|
| `0-0-serialinterfaces-1-assignedmode` | enum int | 0 = not assigned, 1 = RS-232, 2 = RS-485 (depends on the device) |
| `0-0-serialinterfaces-1-assignedowner` | enum int | 0 = None, 1 = CODESYS, 2 = Service |
| `0-0-serialinterfaces-1-currentmode` | enum int | Read-only. Shows the active mode |
| `0-0-serialinterfaces-1-name` | string | Read-only. The label of the port, for example "X3" |
| `0-0-serialserviceinterfaceowner-configured` | enum int | 0 = None, 1 = CODESYS, 2 = Service |

```yaml
plc_ip: 192.168.42.118
managed_parameters:
  0-0-serialinterfaces-1-assignedmode: 1
  0-0-serialinterfaces-1-assignedowner: 1
```

### OpenVPN

The function `gitops.openvpn_params()` makes these values. All device classes have them.

| Parameter | Type | Notes |
|-----------|------|-------|
| `0-0-openvpn-enabled` | bool | Starts the OpenVPN client |
| `0-0-openvpn-isrunning` | bool | Read-only |
| `0-0-openvpn-configurationdescription` | string | A label for the loaded configuration |
| `0-0-openvpn-certificatedescription` | string | A label for the loaded certificate |
| `0-0-openvpn-configfile` | bytes | The `.ovpn` file. Upload it in the WBM, not with WDA |
| `0-0-openvpn-certificate` | bytes | The certificate bundle. Upload it in the WBM, not with WDA |
| `0-0-openvpn-privatekey` | bytes | The private key. Upload it in the WBM, not with WDA |

> Upload the `.ovpn` file, the certificate, and the key in the WAGO Web-Based Management (WBM)
> or with WAGO I/O-CHECK. In GitOps files, use only the descriptions and the enable flag.

```yaml
plc_ip: 192.168.42.116
managed_parameters:
  0-0-openvpn-enabled: false
  0-0-openvpn-configurationdescription: Lab VPN tunnel
```

### FTP and FTPS

| Parameter | Type | Notes |
|-----------|------|-------|
| `0-0-ftp-enabled` | bool | FTP without encryption |
| `0-0-ftps-enabled` | bool | FTP with TLS encryption |

```yaml
plc_ip: 192.168.42.110
managed_parameters:
  0-0-ftp-enabled: false
  0-0-ftps-enabled: true
```

### SSH

| Parameter | Type | Notes |
|-----------|------|-------|
| `0-0-ssh-enabled` | bool | |
| `0-0-ssh-isrootloginallowed` | bool | Set it to `false` to close the root account for SSH |
| `0-0-ssh-isrunning` | bool | Read-only |

### Docker

| Parameter | Type | Notes |
|-----------|------|-------|
| `0-0-docker-enabled` | bool | Needs a reboot before it has an effect |
| `0-0-docker-isrunning` | bool | Read-only |

> After you enable Docker, the PLC needs a reboot.
> After CI applies the desired-state pull request, add an ops file for the reboot.

```yaml
# plcs/192.168.42.116.yaml
plc_ip: 192.168.42.116
managed_parameters:
  0-0-docker-enabled: true
```

```yaml
# ops/reboot-116.yaml
id: c9a4b2e7
proposed_at: 2026-06-21T10:00:00+00:00
proposed_by: agent-claude-code
plc_ip: 192.168.42.116
action: invoke_method
method_id: 0-0-reboot-beginreboot
arguments: {}
requires_human: CRITICAL
approved_by: ''
```

### CODESYS 3

| Parameter | Type | Notes |
|-----------|------|-------|
| `0-0-codesys3-enabled` | bool | Starts the CODESYS 3 runtime. Writeable on the PFC300 (checked) |
| `0-0-codesys3-webserver-enabled` | bool | Starts the web server for the CODESYS WebVisu |

### IPsec

| Parameter | Type | Notes |
|-----------|------|-------|
| `0-0-ipsec-enabled` | bool | |
| `0-0-ipsec-isrunning` | bool | Read-only |

### HMI browser (Edge Controller, WP400, TP600)

The function `gitops.browser_params()` makes these values.

| Parameter | Type | Notes |
|-----------|------|-------|
| `0-0-integratedwebbrowser-startpage` | enum int | 0 = blank, 1 = favorites entry. The TP600 in our rack shows `2`, so read the value first |
| `0-0-integratedwebbrowser-startpagefavorite` | instance_ref int | The number of an entry in the favorites list |
| `0-0-integratedwebbrowser-favorites` | instantiations | List of URLs and labels. Configure it in the WBM |
| `0-0-integratedwebbrowser-monitoring-reconnect` | bool | Connect again after a network loss |
| `0-0-integratedwebbrowser-monitoring-reconnectinterval` | uint | Seconds between two connection attempts |
| `0-0-integratedwebbrowser-security-allowunverifiedcertificates` | bool | Accept self-signed certificates |

```yaml
plc_ip: 192.168.2.136
managed_parameters:
  0-0-integratedwebbrowser-startpage: 1
  0-0-integratedwebbrowser-startpagefavorite: 1
  0-0-integratedwebbrowser-monitoring-reconnect: true
```

### Display (Edge Controller, WP400, TP600)

The Edge Controller has only orientation and screensaver. The WP400 and the TP600 also have brightness.

| Parameter | Type | Notes |
|-----------|------|-------|
| `0-0-display-brightness-backlight` | uint8 | 0-100 percent |
| `0-0-display-brightness-nightmode-enabled` | bool | Lower brightness between the start and end time |
| `0-0-display-orientation` | enum int | 0 = 0°, 1 = 90°, 2 = 180°, 3 = 270° |
| `0-0-display-screensaver-enabled` | bool | |
| `0-0-display-screensaver-idletime` | uint32 | Seconds without input before the screensaver starts |

### Network bridges (read them, do not write them)

The name, label, and MAC address of a bridge are read-only.
The IP configuration and the Ethernet port assignment are writeable. But a wrong value disconnects the PLC from the network, the same as a wrong TCP/IP setting.

| Parameter | Type | Writeable |
|-----------|------|-----------|
| `0-0-networking-bridges-1-name` | string | No |
| `0-0-networking-bridges-1-label` | string | No |
| `0-0-networking-bridges-1-macaddress` | string | No |
| `0-0-networking-bridges-1-connectedethernetports` | instance_ref[] | Yes - dangerous |
| `0-0-networking-bridges-1-ipconfiguration-sources` | enum[] | Yes - dangerous |
| `0-0-networking-bridges-1-ipconfiguration-addresses` | string[] | Yes - dangerous |
| `0-0-networking-bridges-2-*` | different types | Same as bridge 1 |

**Do not put bridge or TCP/IP parameters in a desired-state file.** A wrong value
disconnects the PLC. Then you need physical access to the PLC to repair it.

---

## Functions that WDA does not have

WDA has no parameters for these functions.
Configure them in the WAGO Web-Based Management (WBM) or with WAGO I/O-CHECK:

| Function | Where to configure it |
|---------|-----------------|
| Remote syslog | WBM → System → Syslog |
| Port mapping, iptables, firewall rules | WBM → Networking → Firewall |
| Commissioning service | WBM → Configuration |
| Upload of VPN certificates, keys, and configuration files | WBM → Networking → OpenVPN |
| Browser favorites list | WBM → HMI → Browser |
| SNMP trap receivers | WBM → Management → SNMP |

---

## Run `apply.py`

```bash
# Dry run - show the drift and change nothing
python scripts/apply.py plcs/192.168.42.118.yaml

# Write the drift to the live PLC
python scripts/apply.py plcs/192.168.42.118.yaml --execute

# Run the method, then delete the ops file
python scripts/apply.py ops/a3f1c2d8.yaml --execute
```

`apply.py` reads `DEFAULT_PLC_USERNAME` and `DEFAULT_PLC_PASSWORD` from a `.env` file or from the environment.
Put the `.env` file in the directory of `apply.py` or in a parent directory, or export the variables first.

---

## Safety model - three independent gates

The risk is not that an agent deletes a database.
The risk is an agent that makes a wrong decision, for example because of a hallucination, a prompt injection, or a bug.
Then it can restart or change a PLC at the wrong time. On some production lines, this can damage equipment or cause injury.
The three gates are in the code (`src/safety.py`, `src/main.py`, `scripts/apply.py`). **The agent cannot change them with a prompt.**

### Gate 1 - Dangerous-method denylist (default-deny)

The server treats a method as dangerous in these cases:

- A part of the method ID starts with `reboot`, `restart`, `factory`, `firmware`, or `format`.
- The method belongs to the `update` feature (`0-0-update-*`). The CC100-IEC62443 uses this feature for firmware updates.

| Mode | Behavior |
|---|---|
| Live (`GITOPS_MODE=0`) | **Refused**, unless the exact method ID is in `WAGO_ALLOW_METHODS`. |
| GitOps (`GITOPS_MODE=1`) | **Proposed**. The ops YAML has `requires_human: CRITICAL` and an empty `approved_by`. The audit log records the proposal. |

The list is short on purpose. For example, it does not contain `reset`, because that word also occurs in harmless parameters.
To change the list, edit `src/safety.py`. To allow one method, add its ID to `WAGO_ALLOW_METHODS`.

### Gate 2 - Per-PLC read-only

A PLC in `WAGO_READONLY_HOSTS` (comma-separated), or with `# readonly` on its line in
`WAGO_PLC_HOSTS_FILE`, refuses **both** `set_parameters` and `invoke_method` in **all** modes.
Use this for a production PLC that the agent must never change.

```env
WAGO_READONLY_HOSTS=192.168.42.118,192.168.42.119
```
```text
# fleet.txt
192.168.42.118  # readonly prod line A
```

### Gate 3 - Human approval and audit in `apply.py`

`apply.py` can run a dangerous action, but only after a person approves it:

- `apply.py` **refuses** a dangerous operation if `approved_by` is empty.
  The agent never writes a value in this field. With the CI workflow, the merge sets it from the approving reviewer.
- If `AUDIT_LOG_FILE` is set, `apply.py` adds a record to the tamper-evident audit chain for each run.

### Try it (dry run, no PLC changes)

```bash
# Desired state (not critical) - shows the drift and changes nothing:
python scripts/apply.py docs/gitops/examples/ptxdist/plcs/01-ntp-client.yaml

# Safe method (NTP sync) - no gate, it runs with --execute:
python scripts/apply.py docs/gitops/examples/ptxdist/ops/16-sync-time-now.yaml

# Critical operation, as the agent wrote it - refused, because approved_by is empty:
python scripts/apply.py docs/gitops/examples/ptxdist/ops/20-reboot.yaml --execute
```

We tested all four paths against a live PLC: desired state, safe method, critical refused, and critical approved.
The gate opens only after a person sets `approved_by`.
