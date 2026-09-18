# GitOps write-gate

Use GitOps mode when a person must review each PLC configuration change before it goes to the hardware.
The pattern is similar to ArgoCD.

## How it works

```
Agent proposes a config change
         │
         ▼ (GITOPS_MODE=1)
set_parameters / invoke_method returns YAML instead of writing
         │
         ▼
Agent commits YAML to wago-plc-config repo and opens a PR
         │
         ▼
Engineer reviews and approves the PR
         │
         ▼
CI runs: python scripts/apply.py plcs/192.168.1.10.yaml --execute
         │
         ▼
Live PLC updated - ops files self-delete on success
```

A GitHub Actions workflow in the config repository runs the CI step. The trigger event sets the mode:

- A pull request always does a dry run. It shows the drift and changes nothing.
- A push to `main` (a merge) applies the change.

The workflow uses a **self-hosted runner**, because GitHub-hosted runners cannot reach the PLC subnet.
Each run gets `scripts/apply.py` from this repository with a sparse checkout. A fix here applies there without a version change.
The workflow template is [`docs/gitops/apply.yml`](apply.yml).

## GitOps setup

The MCP server does not store the YAML files and does not include a config repository.
You create the config repository yourself, one time. After that, each change needs a pull request.

You need:

- A GitHub repository that you control. Make it private, because it contains your PLC IP addresses and settings.
- A Linux host that can reach the PLCs, for the self-hosted runner. It needs Python 3.11 or later with `pip`, and `git`. The host can be the same host as the Docker deployment.
- A GitHub tool for Claude, for example the GitHub MCP server or the `gh` CLI in Claude Code. Without a GitHub tool, Claude gives you the YAML and you commit it yourself.

**Step 1 - Create the config repository**

1. Create a new private repository, for example `wago-plc-config`.
2. Make two folders: `plcs/` for desired-state files and `ops/` for one-time actions.
   Git does not keep an empty folder, so add an empty `.gitkeep` file to each.
3. Copy [`docs/gitops/apply.yml`](apply.yml) to `.github/workflows/apply.yml` in the new repository.
   For example files, 20 for each firmware generation (PTXdist and Yocto), see [`docs/gitops/examples/`](examples/README.md).

**Step 2 - Configure the repository on GitHub**

1. Go to **Settings → Secrets and variables → Actions** and add the secrets `PLC_USERNAME` and `PLC_PASSWORD`.
   CI uses this login for every PLC.
2. Optional: on the **Variables** tab, add `AUDIT_SYSLOG` (a syslog target).
   The runner does not keep files between runs, so syslog is the only audit record of the CI writes.
3. Go to **Settings → Actions → General → Workflow permissions** and select **Read and write permissions**.
   CI commits the deletion of `ops/` files after it runs them.
4. Recommended: go to **Settings → Branches** and add a rule for `main` that requires a pull request with one approval.
   Without this rule, the person who proposes a change can also merge it.

**Step 3 - Register a self-hosted runner**

GitHub-hosted runners cannot reach your PLC network.

1. Go to **Settings → Actions → Runners → New self-hosted runner** and select **Linux**.
2. On the host that can reach the PLCs, run the commands that GitHub shows.
3. Install the runner as a service: `sudo ./svc.sh install && sudo ./svc.sh start`.

**Step 4 - Enable GitOps mode in the MCP server**

Docker (`.env` or Portainer stack):

```env
WAGO_ALLOW_WRITES=true   # required: a read-only PLC refuses the request before GitOps mode applies
GITOPS_MODE=1            # 1 = return YAML for a pull request, 0 = write directly (default)
WAGO_GITOPS_REPO=<owner>/wago-plc-config   # the repository from step 1
```

Then recreate the container: `docker rm -f wmcp && docker compose up -d`.

Claude Desktop extension: in the extension settings, select **Allow writes and method calls** and **GitOps mode**.
Enter the repository from step 1 in **GitOps config repository**.

> [!IMPORTANT]
> The agent gets the config repository name only from `WAGO_GITOPS_REPO`. The agent does not find the repository automatically.
> If you do not set it, the `next_step` instructions refer to `wago-plc-config`.

**Step 5 - Test the setup**

1. Ask Claude for a harmless change, for example: "Set the SNMP location of 192.168.1.10 to Test-Rack".
2. Claude replies that it proposed the change, and opens a pull request that changes `plcs/192.168.1.10.yaml`.
3. On the pull request, the **Dry-run** job shows the drift. The PLC does not change.
4. Approve the pull request, then merge it. The **Apply** job writes the change to the PLC.
5. Ask Claude to read the parameter again to confirm the change.

If the **Dry-run** job stays in the **Queued** state, the runner is offline.

## Use GitOps mode

In GitOps mode you ask Claude for changes the same way as in live mode. The difference: Claude never writes to the PLC. It gives you a pull request, and the merge applies it.

**Change a parameter**

1. Ask Claude, for example: "Enable NTP on 192.168.1.10 with time server 192.168.1.1".
2. Claude replies with `status: proposed` and changes `plcs/192.168.1.10.yaml` in a pull request.
   Without a GitHub tool, Claude gives you the file path and the YAML. Commit the change on a branch.
   Then open the pull request yourself.
3. Open the pull request. The **Dry-run** job shows each parameter as `current -> desired`. Nothing changes on the PLC yet.
4. If the **Dry-run** job output is correct, approve the pull request, then merge it. The **Apply** job writes only the parameters that are different.
5. Ask Claude to read the parameters again to confirm the change.

**Run a method (one-time action)**

1. Ask Claude, for example: "Sync the time on 192.168.1.10 now".
2. Claude creates `ops/<id>.yaml` in a pull request.
3. Merge the pull request. CI runs the method once and then deletes the ops file.

**Dangerous methods (reboot, factory reset, firmware)**

The ops file has `requires_human: CRITICAL` and an empty `approved_by`.
`apply.py` refuses to run it without an approver.

1. Review the pull request. Make sure that the time is safe: a reboot stops the machine that the PLC controls.
2. Approve the pull request, then merge it. The merge is the approval: CI records the approving reviewer, or the person who merged, as `approved_by`.
   Claude must never write a value in `approved_by`. If the file already has a name in it, reject the pull request.

If you run `apply.py` by hand instead of through CI, set `approved_by` in the file or set `WAGO_APPROVED_BY`.

**Undo a change**

Open a new pull request that sets the old values in `plcs/<ip>.yaml`. Then merge it.
To remove a parameter from GitOps control, delete its line. CI does not reset a parameter that is no longer in the file.

**Stop a merge that must not run**

- Merge without a PLC call: put `[skip ci]` in the merge commit message.
- Cancel a run that has not started: `gh run list --workflow apply.yml --limit 3`, then `gh run cancel <run-id>`.

## Hands-on example: change the NTP interval on a PFC200

This example uses the PFC200 at `192.168.42.118` in our test rack and the file `plcs/192.168.42.118.yaml` in our config repository.
Before the change, the file contains:

```yaml
plc_ip: 192.168.42.118
# PFC200
managed_parameters:
  0-0-ntpclient-enabled: true
  0-0-ntpclient-configuredtimeservers:
    - 192.168.42.2
  0-0-ntpclient-updateinterval: 300
```

**1. Ask Claude for the change**

> Set the NTP update interval on 192.168.42.118 to 600 seconds.

**2. The server returns a proposal, not a write**

Claude calls `set_parameters`. In GitOps mode, the server does not connect to the PLC for the write. It returns:

```json
{
  "status": "proposed",
  "config_file": "plcs/192.168.42.118.yaml",
  "desired_state_yaml": "plc_ip: 192.168.42.118\nmanaged_parameters:\n  0-0-ntpclient-updateinterval: 600\n",
  "next_step": "Merge desired_state_yaml into WagoAlex/wago-plc-config/plcs/192.168.42.118.yaml (add/update keys under managed_parameters) and open a PR. apply.py will read current PLC state, diff against desired, and apply only what changed."
}
```

**3. Claude opens a pull request**

Claude merges the new value into the file. It keeps the other keys. The pull request contains one changed line:

```diff
   0-0-ntpclient-configuredtimeservers:
     - 192.168.42.2
-  0-0-ntpclient-updateinterval: 300
+  0-0-ntpclient-updateinterval: 600
```

**4. The Dry-run job shows the drift**

The **Dry-run** job reads each parameter in the file from the PLC and compares it with the file.
It shows only the parameters that are different, and it does not write:

```text
[192.168.42.118] Drift detected (1 parameter(s)):
  0-0-ntpclient-updateinterval: 300 → 600

Dry-run - pass --execute to apply.
```

**5. You review and merge**

Make sure that the drift contains only the change that you asked for.
Approve the pull request, then merge it.
The **Apply** job writes the one parameter to the PLC:

```text
[192.168.42.118] Drift detected (1 parameter(s)):
  0-0-ntpclient-updateinterval: 300 → 600
[192.168.42.118] Applied 1 change(s).
```

**6. Claude confirms the change**

Ask Claude to read `0-0-ntpclient-updateinterval` on `192.168.42.118` again. The value is `600`.
If you merge the same file again, the job shows `[192.168.42.118] In sync - nothing to apply.`

## Config YAML files

**`plcs/<ip>.yaml`** sets the desired state:

```yaml
plc_ip: 192.168.1.10
managed_parameters:
  0-0-ntpclient-enabled: true
  0-0-ntpclient-configuredtimeservers:
    - 192.168.1.1
  0-0-snmp-enable: true
  0-0-snmp-communities-1-name: ops-team
  0-0-snmp-location: Building-A-Panel-3
```

`apply.py` reads the live PLC, compares it with this file, and writes only the parameters that are different.
You can run it again with the same result, so CI can run it on each merge.

**`ops/<id>.yaml`** is a one-time action. `apply.py` deletes the file after success.

```yaml
id: b7d3e1f9
proposed_at: 2026-06-21T10:00:00+00:00
proposed_by: agent-claude-code
plc_ip: 192.168.1.10
action: invoke_method
method_id: 0-0-ntpclient-updatetime
arguments: {}
```

## Run apply.py manually

```bash
# Show what would change - no writes
python scripts/apply.py plcs/192.168.1.10.yaml

# Apply drift to live PLC
python scripts/apply.py plcs/192.168.1.10.yaml --execute

# Invoke a one-shot method
python scripts/apply.py ops/b7d3e1f9.yaml --execute
```

## Supported subsystems

| Subsystem | Parameters | Helper |
|-----------|---------------|--------|
| Cloud / MQTT | `0-0-cloudconnections-1-*` | `gitops.cloud_params()` |
| NTP | `0-0-ntpclient-enabled/configuredtimeservers/updateinterval` | `gitops.ntp_params()` |
| SNMP | `0-0-snmp-enable/communities-1-name/location/contact` | `gitops.snmp_params()` |
| Serial port | `0-0-serialinterfaces-1-assignedmode/assignedowner` | `gitops.serial_params()` |
| OpenVPN | `0-0-openvpn-enabled/configurationdescription` | `gitops.openvpn_params()` |
| HMI browser | `0-0-integratedwebbrowser-startpage/startpagefavorite` | `gitops.browser_params()` |
| FTP / FTPS | `0-0-ftpd-enabled/ftps` | direct |
| SSH | `0-0-ssh-enabled` | direct |
| Docker | `0-0-docker-enabled` | direct |
| CODESYS 3 webserver | `0-0-codesys3-webserver-enabled` | direct |

- Parameter IDs and YAML examples for all subsystems: [`docs/gitops/README.md`](reference.md)
- Config repository setup: [GitOps setup](#gitops-setup)
