# How does the WAGO PLC MCP server work? {#how-the-server-works}

The server turns the WDA REST API of each WAGO PLC into **29 MCP tools**, so an AI agent can read and change system settings. It **checks each write in code** before the write reaches a PLC.

- The agent sees named tools. The server handles the HTTP calls, the paging, and the login for each PLC.[](source:client)
- At startup, the server stores the parameter and method IDs of each PLC, so a search does not contact the PLC.[](source:cache)
- The agent cannot remove a safety gate or add a PLC. A person changes these settings and restarts the container.[](source:safety)

@answer scope="Server 2.4.4, commit 015769b. Example output is from a read on a PFC300 with firmware 04.09.01. For readers who are new to this server."
@meta locale=en
@source tools title="MCP tool definitions" url=https://github.com/WagoAlex/wago-plc-mcp-server/blob/015769b42dc1de63020b95f9db0580cf21f6a2bf/src/main.py#L178-L190
@source startup title="Server startup" url=https://github.com/WagoAlex/wago-plc-mcp-server/blob/015769b42dc1de63020b95f9db0580cf21f6a2bf/src/main.py#L916-L950
@source setparams title="set_parameters tool" url=https://github.com/WagoAlex/wago-plc-mcp-server/blob/015769b42dc1de63020b95f9db0580cf21f6a2bf/src/main.py#L434-L472
@source invoke title="invoke_method gates" url=https://github.com/WagoAlex/wago-plc-mcp-server/blob/015769b42dc1de63020b95f9db0580cf21f6a2bf/src/main.py#L598-L616
@source fileref title="File upload gates" url=https://github.com/WagoAlex/wago-plc-mcp-server/blob/015769b42dc1de63020b95f9db0580cf21f6a2bf/src/main.py#L781-L795
@source safety title="Dangerous method rules" url=https://github.com/WagoAlex/wago-plc-mcp-server/blob/015769b42dc1de63020b95f9db0580cf21f6a2bf/src/safety.py#L22-L54
@source auth title="Bearer auth and rate limit" url=https://github.com/WagoAlex/wago-plc-mcp-server/blob/015769b42dc1de63020b95f9db0580cf21f6a2bf/src/auth.py#L142-L193
@source limits title="Rate limit values" url=https://github.com/WagoAlex/wago-plc-mcp-server/blob/015769b42dc1de63020b95f9db0580cf21f6a2bf/src/auth.py#L22-L25
@source register title="PLC registration" url=https://github.com/WagoAlex/wago-plc-mcp-server/blob/015769b42dc1de63020b95f9db0580cf21f6a2bf/src/plc_manager.py#L127-L164
@source cache title="Parameter and method cache" url=https://github.com/WagoAlex/wago-plc-mcp-server/blob/015769b42dc1de63020b95f9db0580cf21f6a2bf/src/plc_manager.py#L166-L259
@source many title="Bounded parallel registration" url=https://github.com/WagoAlex/wago-plc-mcp-server/blob/015769b42dc1de63020b95f9db0580cf21f6a2bf/src/plc_manager.py#L261-L279
@source client title="WDA client login and token refresh" url=https://github.com/WagoAlex/wago-plc-mcp-server/blob/015769b42dc1de63020b95f9db0580cf21f6a2bf/src/wda_client.py#L47-L102
@source paginate title="WDA paging" url=https://github.com/WagoAlex/wago-plc-mcp-server/blob/015769b42dc1de63020b95f9db0580cf21f6a2bf/src/wda_client.py#L123-L148
@source wdaset title="WDA parameter write" url=https://github.com/WagoAlex/wago-plc-mcp-server/blob/015769b42dc1de63020b95f9db0580cf21f6a2bf/src/wda_client.py#L182-L196
@source wdainvoke title="WDA method call" url=https://github.com/WagoAlex/wago-plc-mcp-server/blob/015769b42dc1de63020b95f9db0580cf21f6a2bf/src/wda_client.py#L276-L291
@source enrich title="Enum and status labels" url=https://github.com/WagoAlex/wago-plc-mcp-server/blob/015769b42dc1de63020b95f9db0580cf21f6a2bf/src/enricher.py#L5-L36
@source audit title="Audit record and hash" url=https://github.com/WagoAlex/wago-plc-mcp-server/blob/015769b42dc1de63020b95f9db0580cf21f6a2bf/src/audit.py#L57-L75
@source tls title="Security profile and TLS check" url=https://github.com/WagoAlex/wago-plc-mcp-server/blob/015769b42dc1de63020b95f9db0580cf21f6a2bf/src/config.py#L21-L83
@source gitops title="GitOps YAML fragments" url=https://github.com/WagoAlex/wago-plc-mcp-server/blob/015769b42dc1de63020b95f9db0580cf21f6a2bf/src/gitops.py#L1-L6
@source howitworks title="How it works" url=https://github.com/WagoAlex/wago-plc-mcp-server/blob/main/docs/how-it-works.md
@source security title="Security" url=https://github.com/WagoAlex/wago-plc-mcp-server/blob/main/docs/security.md
@source reference title="Reference: all tools and settings" url=https://github.com/WagoAlex/wago-plc-mcp-server/blob/main/docs/reference.md
@source gitopsdoc title="GitOps" url=https://github.com/WagoAlex/wago-plc-mcp-server/blob/main/docs/gitops/README.md
@source firmware title="Firmware updates" url=https://github.com/WagoAlex/wago-plc-mcp-server/blob/main/docs/firmware-updates.md
@source skill title="WAGO PLC skill: device generations" url=https://github.com/WagoAlex/wago-plc-mcp-server/blob/main/wago-plc-skill/SKILL.md

## Which words do you need first? {#words}

| Word | Meaning | Example |
| --- | --- | --- |
| MCP | A protocol that lets an AI assistant call a fixed set of tools | `get_parameter` |
| WDA | The WAGO REST API for system and diagnostic management | `GET /wda/parameters/{id}` |
| Parameter | One named system value | `0-0-ntpclient-enabled` |
| Method | A remote action on the PLC | NTP sync, reboot |
| Watchlist | A list of parameters that the PLC keeps open for repeated reads | Service health every 30 s |

A parameter ID has a fixed form: `<device>-<instance>-<feature>-<name>`. So `0-0-ntpclient-enabled` is device 0, instance 0, feature `ntpclient`, name `enabled`.[](source:safety)

@callout level=note title="WDA is not the control program"
WDA manages the system layer. It gives no access to control-program I/O tags or real-time process values. For field I/O, use OPC UA or Modbus TCP.

## What are the parts of the server? {#parts}

@architecture id=server-parts title="From the AI agent to the PLC"
| client | MCP client | frontend |
| tools | 29 MCP tools | backend | source:tools |
| cache | PLC manager cache | database | source:cache |
| gates | Safety gates | security | source:safety |
| wda | WDA client | backend | source:client |
| audit | Audit log | database | source:audit |
| repo | Config repository | external | source:gitops |
| plc | WAGO PLC fleet | cloud |
| client > tools | Bearer key | security |
| tools > cache | looks up | |
| tools > gates | writes | |
| tools > wda | reads | |
| gates > wda | passed | emphasis |
| gates > audit | records | |
| gates > repo | GitOps YAML | dashed |
| wda > plc | HTTPS | emphasis |

| File | Job |
| --- | --- |
| `src/main.py` | Defines the tools and starts the server |
| `src/auth.py` | Checks the Bearer key and the rate limit |
| `src/safety.py` | Identifies dangerous methods and read-only PLCs |
| `src/plc_manager.py` | Registers PLCs and stores their IDs |
| `src/wda_client.py` | Sends the WDA requests for one PLC |
| `src/enricher.py` | Adds labels and status text to raw values |
| `src/audit.py` | Writes the hash-chained audit log |
| `src/gitops.py` | Makes YAML proposals for the config repository |
| `src/config.py` | Reads the fleet list, secrets, and TLS settings |

## What happens when the server starts? {#startup}

@workflow id=startup-flow title="Server startup"
| profile | Check security profile | security |
| seed | Seed audit chain | database |
| fleet | Read fleet config | external |
| register | Register each PLC | backend |
| key | Resolve API key | security |
| serve | Serve the tools | backend |
| profile > seed | |
| seed > fleet | |
| fleet > register | |
| register > key | |
| key > serve | |

@steps id=startup-steps
| st-profile | Check security profile | With `SECURITY_PROFILE=hardened`, the server stops if TLS is not complete. | startup-flow | profile |
| st-seed | Seed audit chain | The server reads the last log line, so the hash chain continues after a restart. | startup-flow | seed |
| st-fleet | Read fleet config | The list comes from `WAGO_PLC_HOSTS` and `WAGO_PLC_HOSTS_FILE`. Passwords come from Docker secrets or settings. | startup-flow | fleet |
| st-register | Register each PLC | The server does a login test, then stores the IDs. It registers 5 PLCs at a time by default. | startup-flow | register |
| st-key | Resolve API key | The order is Docker secret, `MCP_API_KEY`, saved file, new key. The stdio transport does not use a key. | startup-flow | key |
| st-serve | Serve the tools | The default is port 6042 at `/mcp`. The `/health` route does not need a key. | startup-flow | serve |

If a PLC fails the login test, or its parameters or methods do not load, the server skips that PLC and continues.[](source:register)[](source:cache)

To change the fleet, edit the list and recreate the container. All PLCs then register again.[](source:many)

## Which tools does the agent get? {#tools}

| Group | Tools | Count |
| --- | --- | --- |
| Fleet and device | `list_plcs`, `describe_plc`, `get_device`, `get_feature` | 4 |
| Read parameters | `find_parameters`, `get_parameter`, `get_parameters_bulk`, `get_parameter_definition`, `get_enum_definition`, `get_parameter_referenced_instances`, `list_parameter_instances`, `get_parameter_instance` | 8 |
| Write parameters | `set_parameters`, `set_parameter` | 2 {caution:Gated} |
| Methods | `find_methods`, `get_method`, `invoke_method`, `get_method_run`, `list_method_runs`, `delete_method_run` | 6 {caution:Gated} |
| Watchlists | `create_watchlist`, `read_watchlist`, `list_watchlists`, `delete_watchlist` | 4 |
| Files | `create_file`, `upload_file`, `download_file`, `get_file_metadata` | 4 {caution:Gated} |
| Audit | `get_plc_audit_log` | 1 |
| **Total** | All groups | **29** |

In the Methods and Files groups, the gates apply only to `invoke_method`, `create_file`, and `upload_file`. The server also gives the agent the `wago://catalog` resource and the `wago_assistant` prompt.[](source:reference)

The usual order is `list_plcs`, `describe_plc`, `find_parameters` or `find_methods`, `get_parameter` or `get_method`, then `set_parameters` or `invoke_method`.

## What happens during a read and a write? {#read-write}

@sequence id=read-write-flow title="Find, read, and write one parameter"
| actor agent | AI agent | frontend |
| actor tools | MCP tools | backend |
| actor cache | PLC manager cache | database |
| actor gates | Safety gates | security |
| actor plc | WAGO PLC | cloud |
| phase | Find: the cache answers |
| agent | tools | find_parameters |
| tools | cache | search IDs |
| tools | agent | matching IDs | return |
| phase | Read: the PLC answers |
| agent | tools | get_parameter |
| tools | plc | GET /wda/parameters/{id} |
| plc | tools | raw value | return |
| tools | agent | value and labels | return |
| phase | Write: the gates check first |
| agent | tools | set_parameters |
| tools | gates | read-only PLC? |
| gates | plc | PATCH /wda/parameters | emphasis |
| plc | agent | 204, then status ok | return |

```json title="Real get_parameter result"
{
  "dataRank": "scalar",
  "dataType": "boolean",
  "path": "NTPClient/Enabled",
  "value": true,
  "status": "Activated",
  "writeable": true
}
```

WDA returns the raw value. The server adds `status`, `path`, and `writeable`. For an enum, it also adds the text label.[](source:enrich)

Before it sends a write, the server checks the cache. It refuses an unknown ID and a parameter that is not writeable. So a bad write does not reach the PLC.[](source:setparams)

## When does the server allow a write? {#gates}

@workflow id=method-gates title="Gates of invoke_method"
| call | invoke_method | external |
| readonly | PLC read-only? | security |
| gitops | GitOps mode? | backend |
| dangerous | Dangerous method? | security |
| refused | Refused | security |
| proposal | YAML proposal | external |
| run | Runs on the PLC | backend |
| call > readonly | |
| readonly > refused | yes | security |
| readonly > gitops | no | |
| gitops > proposal | yes | dashed |
| gitops > dangerous | no | |
| dangerous > refused | yes | security |
| dangerous > run | no | emphasis |

| Condition | Read | `set_parameters` | Safe method | Dangerous method | File upload |
| --- | --- | --- | --- | --- | --- |
| **Read-only PLC**, all modes | Allowed | **Refused** | **Refused** | **Refused** | **Refused** |
| **Live mode** (default) | Allowed | Allowed if writeable | Allowed | **Refused**, unless in `WAGO_ALLOW_METHODS` | Allowed |
| **GitOps mode** | Allowed | YAML proposal | YAML proposal | YAML proposal with `requires_human: CRITICAL` {caution:Person approves} | **Refused** |

A dangerous method has a segment that starts with `reboot`, `restart`, `factory`, `firmware`, or `format`. All `0-0-update-*` methods are also dangerous.[](source:safety)

A read-only PLC comes from `WAGO_ALLOW_WRITES`, `WAGO_READONLY_HOSTS`, or `# readonly` in the fleet file. Any `WAGO_ALLOW_WRITES` value other than `true` blocks writes.[](source:howitworks)

In GitOps mode, the tool returns YAML. The agent commits it to the config repository and opens a pull request. CI applies the change after the merge.[](source:gitopsdoc)

@callout level=warning title="A refusal is correct behavior"
If the agent reports a refusal, do not change the gate to continue. Use a reviewed pull request for the action.

## Which WDA details cause problems? {#wda-details}

The WDA client handles these details, so the agent never sees them. You need them only for a change to `src/wda_client.py` or for a test with `curl`.

| Task | Correct call | Trap |
| --- | --- | --- |
| Connect | `https://<PLC_IP>/wda` | HTTP returns `426` |
| Log in | Basic auth, then the `WAGO-WDX-Auth-Token` as a Bearer token | After a `401`, the client gets a new token one time |
| Write | `PATCH /wda/parameters` | Success is `204` with an empty body. `POST` returns `405`. |
| Call a method | `POST /wda/methods/{id}/runs?result-behavior=sync` | Wrap each argument: `{"value": ...}` |
| Read many | Follow `links.next` | WDA sends at most 255 entries in a page |
| Read parameters | Add `parameter-errors-as-data-attributes=true` | Without it, one unreadable parameter can fail the full page |

[](source:client)[](source:paginate)[](source:wdaset)[](source:wdainvoke)

## How does the server protect itself and record changes? {#security}

| Connection or control | Default | Stronger setting |
| --- | --- | --- |
| Client to server | Bearer key, 60 requests a minute for each IP address, no TLS | Set `MCP_TLS_CERT` and `MCP_TLS_KEY` |
| Server to PLC | HTTPS without a certificate check {caution:Not verified} | Set `WAGO_TLS_CA`, or a `plc_cert_<ip>` Docker secret |
| Startup | Warnings only | `SECURITY_PROFILE=hardened` refuses to start without TLS |
| Local stdio | No network connection, so no key | Not necessary |
| Audit log | Local hash chain in `/app/data/audit.log` | Set `AUDIT_SYSLOG` for a second copy on another host |

[](source:limits)[](source:tls)[](source:security)

Each audit line stores the SHA-256 hash of the line before it. If someone changes an old line, the check fails at the next line. The server removes passwords before it calculates the hash.[](source:audit)

```text title="How the chain connects"
line 1: {"action": "set_parameters", "result": "ok", "prev": "<start value>"}
line 2: {"action": "invoke_method", "result": "denied: dangerous method", "prev": "<SHA-256 of line 1>"}
line 3: {"action": "set_parameters", "result": "ok", "prev": "<SHA-256 of line 2>"}
```

```bash title="Verify the audit log"
docker exec wmcp python /app/src/audit_verify.py --log /app/data/audit.log
```

## Why can the same request need different parameters? {#generations}

WAGO devices use two firmware generations. A parameter ID from one generation can be missing on the other.[](source:skill)

| Item | PTXdist | Yocto |
| --- | --- | --- |
| Example device | CC100 `751-9401` | CC100-IEC62443 `751-9412` |
| Firmware format | `04.09.01` (build 31) | `02.00.13` |
| Parameter count on the same hardware line | About 360 | About 1056 |
| DNS servers | One flat parameter: `0-0-networking-dns-customdnsservers` | One for each bridge: `0-0-networking-bridges-<N>-nameservers-dns` |
| I/O channel role | Fixed | Configurable: `0-0-io-channelcompositions-<N>-channels` |

Before you write to an unfamiliar PLC, read `0-0-version-firmwareversion`. Then search for the feature with `find_parameters`. Do not reuse a parameter ID from another generation without this check.

## What does the server not do? {#limits}

- It does not read or write control-program I/O tags, process values, or PLC memory.
- It supports WAGO devices only. It is not an HMI or a SCADA system.
- It does not let an agent add or remove a PLC.
- It does not flash firmware. A person or CI runs the separate `fwupdate` tool. See `docs/firmware-update-overview.html`.[](source:firmware)

## How can you try it safely? {#try-it}

Use a test PLC. These requests read data only.

| Ask the agent | Tool | Expected result |
| --- | --- | --- |
| List my PLCs. | `list_plcs` | The IP addresses of the registered PLCs |
| Describe 192.168.1.10. | `describe_plc` | Device class, parameter count, feature names |
| What firmware runs on 192.168.1.10? | `find_parameters`, `get_parameter` | A value such as `04.09.01` |
| Is NTP on for 192.168.1.10? | `get_parameter` | `status: Activated` or `Deactivated` |
| Show the last audit entries. | `get_plc_audit_log` | Recent writes, method calls, and refusals |

@callout level=warning title="Do not test the gates with a real reboot"
A request for a dangerous method can run if `WAGO_ALLOW_METHODS` contains that method. Before you test a refusal, make sure that the setting is empty and that the machine is stopped.

## Can you explain these points now? {#check-yourself}

- [ ] Why `find_parameters` does not contact the PLC.
- [ ] Which fields the server adds to a raw WDA value.
- [ ] Why a write to an unknown parameter never reaches the PLC.
- [ ] Which three results `invoke_method` can give for a dangerous method.
- [ ] How the audit log shows that someone changed an old line.
- [ ] Why the agent cannot flash firmware.
- [ ] Why you check the firmware format before you reuse a parameter ID.
