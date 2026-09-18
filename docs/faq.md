# FAQ

<details>
<summary><strong>Can the AI change my control program or process I/O values?</strong></summary>

**No.** The WDA REST API has no access to the CODESYS runtime, PLC variables, fieldbus I/O, or your control program.
Field I/O uses OPC UA, Modbus TCP, or WAGO I/O-Check.

</details>

<details>
<summary><strong>What if the AI writes a wrong value?</strong></summary>

The audit log records each write with the timestamp, parameter ID, value, and API key.
For most WDA parameters, you can write the correct value again.
Before a disruptive action, for example a reboot, the assistant asks for your confirmation.
The server refuses firmware updates from the agent. See [Firmware updates](firmware-updates.md#firmware-updates).

</details>

<details>
<summary><strong>Does the server need internet access?</strong></summary>

No. All traffic is local: AI client → MCP server (port 6042) → PLCs (port 443, HTTPS).
The server makes no cloud calls and sends no telemetry.
You can use it on an air-gapped OT network after you copy the Docker image to the host.

</details>

<details>
<summary><strong>Our PLCs have different passwords. How do we configure this?</strong></summary>

```env
DEFAULT_PLC_PASSWORD=wago                         # applied to all PLCs unless overridden
PLC_PASSWORDS=192.168.1.11=secret,192.168.1.12=other
PLC_PASSWORDS_FILE=/app/data/passwords.txt        # one ip=password per line, for many units
```

In Docker, use per-PLC secrets (`secrets/plc_password_<ip_underscores>.txt`). They have priority over all the variables above.
In the Claude Desktop extension, use the **Per-PLC passwords file** field.

</details>

<details>
<summary><strong>Which firewall rules does IT need to open?</strong></summary>

| Direction | Source | Destination | Port | Protocol |
|---|---|---|---|---|
| Inbound | Engineer workstations | MCP server host | 6042 | TCP |
| Outbound | MCP server host | WAGO PLC IPs | 443 | TCP (HTTPS) |

</details>

<details>
<summary><strong>Can many engineers use one server?</strong></summary>

Yes. Deploy one container on a host that can reach the OT network.
Each engineer connects a client to `http://<server>:6042/mcp`.
You can use one shared API key. For traceability in the audit log, give each engineer a different key.

</details>

<details>
<summary><strong>Which firmware version is necessary?</strong></summary>

Firmware build **28 or higher** (`04.xx.xx(28)` or later).
Find the build number in the web interface of the PLC under *Device Information*.
You can also ask the assistant: *"What firmware version is PLC 192.168.x.x running?"*

</details>
