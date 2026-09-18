# Claude Desktop and Claude Code

This page shows how to connect Claude to your PLCs and what you can ask.

![Overview demo](media/demo-overview.gif)

## Quick start

The Claude Desktop extension is the recommended path for one engineer and a small number of PLCs.
You do not need a terminal, Docker, or Python.
For a shared server, go to [Deployment options](deployment.md#deployment-options).

### Step 1 - Install the extension

1. Download `wago-plc-mcp-server-<version>.mcpb` from the [latest release](https://github.com/WagoAlex/wago-plc-mcp-server/releases/latest).
2. Open Claude Desktop and go to **Settings → Extensions**.
3. Drag the `.mcpb` file onto the window. You can also double-click the file.

![Installing the WAGO PLC extension in Claude Desktop](media/demo-mcpb-install.gif)

> [!NOTE]
> Some Windows builds of Claude Desktop do not start the installer from drag-and-drop or double-click.
> This is a Claude Desktop bug. If this occurs, do these steps:
> 1. Unzip the `.mcpb` file.
> 2. Go to **Settings → Extensions → Advanced settings → Install Unpacked Extension**.
> 3. Select the unzipped folder.

### Step 2 - Complete the install form

You must supply the PLC IP address, the WBM username (usually `admin`), and the password.
All other fields have default values.

**A small number of PLCs with the same password:**

1. Type the IPs in **PLC IP addresses**. Use commas between IPs, for example `192.168.1.10,192.168.1.11`.
2. Type the password in **Default PLC password**.

**Many PLCs, or PLCs with different passwords:**

1. Make a text file with one IP on each line, for example `~/.wago-plc-mcp/plc_hosts.txt`:

   ```
   # One IP per line. Lines starting with '#' are comments.
   192.168.1.10   # PFC200 - packaging line
   192.168.1.11   # PFC200 - packaging line
   192.168.1.12   # CC100 - utility room
   192.168.1.20   # Edge Controller - line 2
   192.168.1.21   # Edge Controller - line 2
   ```

2. If some PLCs use a different password, make a second file, for example `~/.wago-plc-mcp/plc_passwords.txt`:

   ```
   # One 'ip=password' pair per line. Only list PLCs that differ from the
   # "Default PLC password" field above - everything else uses that instead.
   192.168.1.12=a-different-password-for-this-one
   ```

3. Select the files with the **Browse...** buttons next to **PLC IP list file** and **Per-PLC passwords file**.

The server merges the IP field and the IP file. You can use both.

> [!WARNING]
> The IPs and passwords above are examples. Replace them with your values.
> Do not commit a filled-in password file to a public location.

**Writes:** Keep **Allow writes and method calls** off if Claude must only read the PLCs.
When this setting is off, the server refuses and logs all parameter writes, method calls, and file uploads.

**GitOps mode:** If a person must review each change before it goes to a PLC, select **GitOps mode**.
Then Claude does not write to the PLC. It returns a YAML file for a pull request in your config repository.
This setting has an effect only when **Allow writes and method calls** is on.
For more information, see [GitOps write-gate](gitops/README.md#gitops-write-gate).

### Step 3 - Ask a question

Save the form. Then ask Claude in plain English:

> "List my PLCs"
> "What firmware is running on 192.168.1.10?"
> "Check NTP status across the fleet"

### Step 4 - Install the WAGO skill (recommended)

The skill tells Claude the WAGO parameter names, the safe operating rules, and how the tools behave.
With the skill, Claude finds the correct parameter faster.

1. Download `wago-plc-skill-<version>.skill` from the [latest release](https://github.com/WagoAlex/wago-plc-mcp-server/releases/latest).
2. In Claude Desktop, go to **Settings → Skills**.
3. Add the downloaded file.

For Claude Code, claude.ai, and the Agent SDK, see [WAGO skill](deployment.md#wago-skill).

## Example questions

You do not need parameter IDs or WDA API knowledge.
The assistant selects the tools and sends the REST calls.

### Fleet-wide checks

| You type | The assistant does this |
|---|---|
| "Which PLCs are running firmware older than build 31?" | Reads the firmware version from all PLCs in parallel and lists the old ones |
| "Are NTP and Docker running on all Edge Controllers?" | Reads the service running flags across the fleet and shows stopped services |
| "Show the diagnostic LED states on all PLCs" | Reads the SYS, RUN, and fieldbus LED text from all units |
| "Is any controller showing a fault or error state?" | Compares LED text and error parameters across the fleet |

### Diagnostics on one PLC

| You type | The assistant does this |
|---|---|
| "What firmware version is running on 192.168.1.14?" | Reads the firmware version parameter |
| "List all network settings on Edge Controller .19" | Searches parameters by keyword and returns names and values |
| "Is the CODESYS program loaded and running on PFC300 .22?" | Reads the CODESYS runtime state parameter |
| "What NTP server is configured on PLC .10?" | Reads the NTP client configuration |

### Configuration changes and remote actions

| You type | The assistant does this |
|---|---|
| "Set the NTP server to 192.168.0.1 on all PLCs in building A" | Writes the NTP address after you confirm. The audit log records each write. |
| "Trigger an NTP time sync on the three controllers that showed clock drift" | Starts the NTP sync method only on the affected units |
| "Enable SSH on controller .14 for remote maintenance access" | Finds the SSH enable parameter and writes it after you confirm |

### Monitoring

| You type | The assistant does this |
|---|---|
| "Set up a health monitor for the packaging line PLCs" | Makes a watchlist on each PLC with LED states, service flags, and cloud status. Each poll is one HTTP request. |
| "Track the firmware update progress on all 12 PLCs" | Polls the update status and progress across the fleet |

> [!NOTE]
> The assistant asks for your confirmation before it writes a value to a PLC.

## Demos

These screen recordings show Claude Desktop with real WAGO PLCs. We did not remove steps.

<details>
<summary><strong>Fleet health report across 16 PLCs</strong></summary>

The agent lists all PLCs, reads the firmware versions in bulk, and checks the device types.
It confirms what runs where before it gives conclusions.

![Use case 1 demo](media/demo-use-case-1.gif)

</details>

<details>
<summary><strong>CPU and LED health watchlist on an Edge Controller</strong></summary>

The agent makes a watchlist for CPU, service health, and LED state, then reads it.
The agent asks questions about unclear requirements before it changes anything.
It finds the parameter IDs with `find_parameters` and does not guess them.

![Use case 2 Edge Controller demo](media/demo-use-case-2-edge-controller.gif)

</details>

<details>
<summary><strong>CPU and LED health watchlist on a PFC300</strong></summary>

This is the same workflow on a PFC300.
The agent finds different parameter names for the same function.

![Use case 2 PFC300 demo](media/demo-use-case-2-pfc300.gif)

</details>

<details>
<summary><strong>Find and fix NTP drift across the fleet</strong></summary>

The agent first checks the NTP status on all PLCs.
It finds the affected units, for example clocks that stopped or wrong timezone offsets.
Then it starts the time sync only on those units.

![Use case 3 demo](media/demo-use-case-3.gif)

</details>

<details>
<summary><strong>Reachability and firmware versions</strong></summary>

The agent calls `list_plcs`, then `describe_plc` on all PLCs in parallel.
It returns a table with the status, model, and firmware build of each PLC.

![Use case 4 demo](media/demo-use-case-4.gif)

</details>

<details>
<summary><strong>Find devices with the default NTP server</strong></summary>

The agent checks the NTP configuration on all PLCs.
It shows each PLC that still uses the factory-default time server.

![Use case 5 demo](media/demo-use-case-5.gif)

</details>
