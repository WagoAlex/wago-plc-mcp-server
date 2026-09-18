# Firmware updates

You cannot undo a firmware update with a new commit. For this reason, the agent cannot start one.

`invoke_method` refuses all `firmware*` methods in live mode on all devices. The audit log records each refusal.
Do not change this setting.

```
> Update the firmware on 192.168.42.121

Method '0-0-firmwareupdate-activate' is denied by safety policy
(dangerous; not in WAGO_ALLOW_METHODS).
```

A person does firmware updates with a separate tool, [`fwupdate/`](../fwupdate/README.md), during a maintenance window.
The agent cannot access this tool.
The tool does not start if the config repository has no committed approval for that device and firmware revision.

The tool writes to the **same hash-chained audit log** as `set_parameters` and `invoke_method`.
It records the approval, each refusal, success, device failure, timeout, and abort.
Each record names the approver and the source of the approval, for example the pull request and its reviewers.

```bash
docker exec wmcp python /app/src/audit_verify.py --log /app/data/audit.log
# [PASS] Chain intact - 13 entries verified

git show 18d2cbf        # who approved it, and when
```

## Update firmware from a Windows or Linux laptop

This procedure uses the published image
[`wagoalex/wago-plc-mcp-server-fwupdate`](https://hub.docker.com/r/wagoalex/wago-plc-mcp-server-fwupdate).
The commands are the same in PowerShell on Windows and in a Linux shell.
You do not need Python.

### Requirements

| Item | Windows 10 / 11 | Linux |
|---|---|---|
| Docker | [Docker Desktop](https://docs.docker.com/desktop/setup/install/windows-install/) with the WSL 2 backend and Linux containers | [Docker Engine](https://docs.docker.com/engine/install/) with the Compose plugin |
| Git | [Git for Windows](https://git-scm.com/downloads/win) | The `git` package of your distribution |
| Network | HTTPS (port 443) from the laptop to each PLC | Same |
| Firmware | The update files for your devices, from WAGO: `.wup` files, or `.zip` bundles for the CC100-IEC62443 | Same |
| PLC access | The WBM user name and password of each PLC | Same |

> [!NOTE]
> Docker Desktop needs a paid subscription in larger companies. Read the
> [Docker Desktop license terms](https://docs.docker.com/subscription/desktop-license/) before you install it.

### Step 1 - Get the files

Open PowerShell (Windows) or a terminal (Linux). Then run these commands:

```bash
mkdir wago
cd wago
git clone https://github.com/WagoAlex/wago-plc-mcp-server.git
cd wago-plc-mcp-server/fwupdate
cp _env .env
mkdir firmware
docker compose pull
```

Copy your firmware files (`.wup`, or `.zip` for the CC100-IEC62443) into the `firmware` folder that you made.
Git ignores this folder, so the large files do not go into a commit.

### Step 2 - Make the approval repository

The tool flashes a PLC only if a committed file approves that PLC and that firmware version.

1. Show the version of each firmware file:

   ```bash
   docker compose run --rm --entrypoint python fwupdate build_catalog.py /firmware /tmp/catalog.json
   ```

   The output shows `rev=4.9.1` for each file, or `rev=02.00.13` for a CC100-IEC62443 bundle. Use this value exactly as the version.

2. Make the repository next to `wago-plc-mcp-server`:

   ```bash
   cd ../..
   mkdir wago-plc-config
   cd wago-plc-config
   git init
   ```

3. In this folder, make a file with the name `.gitattributes` and this content:

   ```
   *.yaml text eol=lf
   ```

4. In the same folder, make a file with the name `firmware-policy.yaml`. Add one line for each PLC:

   ```yaml
   approvals:
     192.168.1.10: "4.9.1"
   ```

5. Commit the two files:

   ```bash
   git add .gitattributes firmware-policy.yaml
   git commit -m "Approve firmware 4.9.1 for 192.168.1.10"
   ```

> [!IMPORTANT]
> On Windows, Git changes line endings to CRLF when it writes a file.
> The Linux container then sees a changed file and refuses the update with "has uncommitted changes".
> The `.gitattributes` file in step 3 prevents this. Commit it before or together with the policy file.

If Git asks for your name and email, set them one time with
`git config --global user.name "Your Name"` and `git config --global user.email you@example.com`.

For a team, push this repository to your Git server and approve changes with pull requests.
The audit log then shows the reviewer. See the [wago-plc-config README](https://github.com/WagoAlex/wago-plc-config#guide-approve-a-firmware-update).

### Step 3 - Configure the connection

Go back to the `fwupdate` folder and open `.env` in a text editor:

```bash
cd ../wago-plc-mcp-server/fwupdate
```

Set these values:

```env
PLC_IP=192.168.1.10
PLC_USERNAME=admin
PLC_PASSWORD=your-plc-password
```

Keep `FIRMWARE_HOST_DIR=./firmware` and `POLICY_HOST_DIR=../../wago-plc-config`.
These values are the paths to the folders from steps 1 and 2.

Make sure that the laptop can reach the PLC:

```bash
docker compose run --rm --entrypoint python fwupdate -c "import os, httpx; print(httpx.get('https://' + os.environ['PLC_IP'] + '/wda', verify=False, timeout=10).status_code)"
```

- A number, for example `401`, means that the PLC is reachable.
- An error, for example `ConnectTimeout`, means that the PLC is not reachable. Check the IP address, the network cable or VPN, and the firewall.

### Step 4 - Do a dry run

A dry run uploads the firmware and checks it. Then it cancels the update. The PLC does not restart.

```bash
docker compose run --rm -e DRY_RUN=true fwupdate
```

The last line must be `==> Dry run complete. Upload pipeline verified; Start was never called.`

### Step 5 - Update the PLC

> [!WARNING]
> Before you start, do these steps:
> - Connect the laptop to mains power.
> - Set the laptop to not sleep. Sleep or a network interruption stops the tool during the update.
> - Stop the machine or process that the PLC controls. The PLC restarts during the update.
> - Do not press Ctrl+C and do not close the window until the tool shows `==> Done.`

```bash
docker compose run --rm fwupdate
```

The update takes 5 to 15 minutes for each PLC.
The last line shows the status and the new firmware version.

### Update many PLCs

Add each PLC to `firmware-policy.yaml` and commit the file. Then run:

```bash
docker compose run --rm -e DRY_RUN=true fleet
docker compose run --rm fleet
```

The tool updates the approved PLCs one after the other.
All PLCs use `PLC_PASSWORD` from `.env`.

### Check the audit log

Each run adds records to `wago-plc-mcp-server/data/audit.log`. Run this command in the `wago-plc-mcp-server` folder to make sure that nobody changed the log:

```bash
docker run --rm -v "${PWD}/data:/app/data:ro" wagoalex/wago-plc-mcp-server python src/audit_verify.py --log /app/data/audit.log
```

### Troubleshooting

| Message | Cause | Action |
|---|---|---|
| `has uncommitted changes` | You changed the policy file and did not commit it, or the file has CRLF line endings on Windows | Commit the change. On Windows, add `.gitattributes` (step 2), then delete `firmware-policy.yaml` and run `git checkout firmware-policy.yaml`. |
| `is not inside a git repository` | `POLICY_HOST_DIR` is not the path of the approval repository | Correct `POLICY_HOST_DIR` in `.env` |
| `required env var PLC_IP is not set` | `.env` is missing or incomplete | Do step 3 again |
| `ConnectTimeout` or `ConnectError` | The laptop cannot reach the PLC | Check the IP address, cable, VPN, and firewall |
| `No bundle in catalog lists order number` | The `firmware` folder has no firmware file for this device | Add the correct `.wup` or `.zip` file |
| `bundles match order number ... Set TARGET_VERSION` | The `firmware` folder has more than one file for this device | Add `-e TARGET_VERSION=4.9.1` to the command |
| `Device is already at ... nothing to do` | The PLC already has this version | No action is necessary |
| `below the minimum` | The PLC needs an intermediate firmware version first | Update to the version in the message first |

For all settings and failure cases, see [`fwupdate/README.md`](../fwupdate/README.md).

## More information

| Question | Document |
|---|---|
| Who approves an update, and how do I require two approvers? | [wago-plc-config README](https://github.com/WagoAlex/wago-plc-config#guide-approve-a-firmware-update) |
| How do I run an update, and what do I do if it fails? | [`fwupdate/README.md`](../fwupdate/README.md) |
| What do the REST calls do? | [`docs/wda-firmware-update.md`](wda-firmware-update.md) |
| I know GitHub but not CI/CD. Where do I start? | [`docs/plc-change-control.html`](plc-change-control.html) |
