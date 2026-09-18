---
name: wago-plc
description: >-
  Use whenever you need to check on, read from, write to, or monitor a WAGO
  PLC (PFC200, PFC300, CC100, CC100-IEC62443, Edge Controller, WP400, TP600)
  via the wago-plc MCP server - plain-English chat requests ("what's the
  firmware on 192.168.1.10?", "turn on NTP sync", "watch the LED every 30
  seconds", "list my PLCs") or programmatic agent calls. Covers
  finding/describing PLCs, reading and writing parameters safely, invoking
  methods, watchlists, and the tool I/O contract (batching, error handling,
  retries). Critically covers recognizing WAGO's fleet spans two firmware
  generations (PTXdist and Yocto) with different parameter shapes for the
  same concept - the same request can need a different path per device. Use
  even without the words WAGO or PLC if the conversation is about an
  industrial controller or factory-floor device by IP. Does not cover raw
  WDA REST/HTTP internals - this is the MCP tool layer, not the protocol.
license: MPL-2.0
compatibility: >-
  Requires the wago-plc-mcp-server MCP server connected and reachable to
  your WAGO PLC fleet network - via Claude Code (.mcp.json), Claude Desktop
  (.mcpb extension or manual config), or any other MCP-capable client or
  Agent SDK. The skill itself needs no local runtime; it only calls the
  connected server's tools (list_plcs, get_parameter, set_parameters, etc.).
metadata:
  version: "2.4.1"
---

# WAGO PLC Assistant

You have access to a WAGO PLC MCP server. It lets you look up, read, write,
and monitor settings on WAGO industrial controllers - in plain language from
a chat UI, or as structured tool calls from an autonomous agent - without
scripting raw REST calls by hand.

## The golden rule: find the PLC first

If you don't have an IP address, **always start with `list_plcs`** to see
what's available, then `describe_plc` on the one you mean. Don't guess an
IP. In a chat UI, if there's more than one PLC and it's not obvious which
one the user wants, ask - don't pick one silently. In an agent pipeline,
don't skip `describe_plc` before reasoning about what a PLC supports:
`device_class`, `feature_count`, and `parameter_count_ok` are cheap (cached,
no network round-trip) and prevent wasted calls against parameters or
methods that don't exist on that device class.

```
list_plcs
  → describe_plc(plc_ip)                       # cheap, cached - call first
    → find_parameters / find_methods            # resolve fuzzy queries to exact IDs
      → get_parameter / get_method               # inspect before acting
        → set_parameters / invoke_method          # act
          → get_method_run                         # poll if invoked with wait=False
```

## Device generations: PTXdist vs. Yocto - check this before touching an unfamiliar PLC

WAGO's fleet is not one firmware family. Two generations coexist, and they
expose meaningfully different WDA parameter models for the *same* concept -
a parameter ID that works on one will not exist, or will mean something
different, on the other. Never assume a parameter ID validated on one
device carries over to a device you haven't checked.

**Don't key off the IP address or subnet** - that's an artifact of one
specific test rack's addressing, not a general rule. Instead, check these
observable signals (in order of speed):

1. **`0-0-version-firmwareversion` format.** PTXdist-family devices report
   a version like `04.09.01`, which maps to WAGO's "build NN" numbering
   (e.g. `04.09.01` = build 31) - this is the baseline most of the fleet
   runs. A version that doesn't fit that pattern (e.g. `02.00.13`) belongs
   to a separate, Yocto-based firmware line - don't try to place it on the
   build-NN scale, and re-verify every parameter path against the live
   device rather than assuming PTXdist-baseline names apply.
2. **`find_parameters(plc_ip, query="channelcomposition")`.** Empty on
   PTXdist devices - their I/O channel role (DI vs. DO, measurement type)
   is fixed and not runtime-configurable via WDA. Non-empty on Yocto
   devices - I/O terminals are modeled as objects: `0-0-io-channels-<N>-*`
   for each logical channel, `0-0-io-channelcompositions-<N>-channels` as a
   **writable array of channel-instance IDs** that lets the same physical
   pin swap between its DI-role and DO-role channel instance, and analog
   channels reference a numbered `0-0-io-analogoperationmodes-<N>-name`
   catalog (e.g. Pt1000=13, Ni100=20) instead of a plain enum string. To
   change a physical pin's DI/DO role or an analog channel's measurement
   type, find its owning composition/catalog via `find_parameters` and
   `get_feature` first - don't guess the instance numbers.
3. **DNS lives in a different place.** PTXdist devices have one flat,
   device-wide `0-0-networking-dns-customdnsservers` /
   `-utilizeddnsservers` pair. Yocto devices have **no such flat
   parameter** - DNS is per-bridge:
   `0-0-networking-bridges-<N>-nameservers-dns` /
   `-currentdns`, plus a per-bridge `-ipconfiguration-dhcpv4options-usedns`
   toggle. Before writing DNS on a Yocto device, read
   `0-0-networking-bridges-<N>-ipconfiguration-currentaddresses` for each
   bridge to find which one actually carries the address you're managing -
   don't assume bridge 1 is "the" network interface.
4. **Parameter count is a rough tell, not proof.** PTXdist base units run
   ~360-410 parameters; a Yocto-based hardened variant on the same hardware
   line can expose 3x that (~1050-1070) for the same physical unit, because
   the object-oriented model above adds many small per-instance parameters
   the flat model doesn't have. A device reporting far more than the
   `describe_plc` baseline isn't necessarily broken - check signal #1/#2
   before assuming something is wrong.

**Docker (`0-0-docker-enabled` / `-isrunning`) exists on both generations**
- it is not a distinguishing signal.

**Practical workflow for an unfamiliar PLC:** read `firmwareversion` and
`identity-ordernumber` via `describe_plc`/`get_parameter`, form a hypothesis
about which generation you're on, then confirm with one cheap
`find_parameters` call for the feature you actually need (`channelcomposition`,
`networking-bridges`, etc.) before writing anything. This mirrors how the
project's own `docs/*-fw31-parameters-raw.json` cassettes are organized -
one baseline per device class/firmware, never assumed to generalize without
checking.

## What you can do, in plain language

| User says something like… | Tool to use |
|---|---|
| "What PLCs do we have?" / "List my controllers" | `list_plcs` |
| "What can this PLC do?" / "Give me an overview of 192.168.1.10" | `describe_plc` |
| "Find anything about NTP / DNS / firmware on this PLC" | `find_parameters` |
| "What's the [setting] on [PLC]?" | `get_parameter` |
| "Check [setting] across all PLCs" | `get_parameters_bulk` |
| "Turn on/off / change [setting] on [PLC]" | `set_parameters` |
| "What actions can I trigger on this PLC?" | `find_methods` |
| "What does [action] need / what does it return?" | `get_method` |
| "Reboot it" / "Sync the clock" / "Run [action]" | `invoke_method` |
| "Is that action done yet?" | `get_method_run` (only for actions run with `wait=False`) |
| "Keep an eye on [these settings] and update me" | `create_watchlist` then `read_watchlist` repeatedly |
| "Stop watching that" | `delete_watchlist` |

You don't need to memorize parameter IDs - `find_parameters` and
`find_methods` do fuzzy/substring search, so "find anything about NTP" or
"find the reboot method" works even without knowing the exact name. This
matters more than usual here: the same plain-English request can resolve to
a different parameter ID depending on the device generation (see above), so
searching beats guessing even when you think you already know the ID from a
previous PLC.

## Programmatic / agent tool contract

For an autonomous agent or pipeline, tool output is structured data, not
prose - here are the exact shapes.

| Tool | Required args | Returns | Network cost |
|---|---|---|---|
| `list_plcs` | - | `{"plcs": [ip, ...]}` | none (cache) |
| `describe_plc` | `plc_ip` | counts + `device_class`, `expected_parameter_count`, `parameter_count_ok` (floor check, not exact match - see below), `features: [str]` | none (cache) |
| `find_parameters` | `plc_ip` | `{"matches": [id, ...], "total_in_pool": int, "truncated": bool}` | none (cache) |
| `get_parameter` | `plc_ip`, `parameter_id` | `{"value", "dataType", "dataRank", "path", "writeable"}` | 1 round-trip |
| `get_parameters_bulk` | `requests: [{"plc_ip","parameter_id"}, ...]` | list of enriched dicts; per-item failures are `{"plc_ip","parameter_id","error"}` and do **not** abort the batch | N concurrent round-trips |
| `set_parameters` | `plc_ip`, `parameters: [{"id","value"}, ...]` | per-parameter status; pre-validates writeability before sending | 1 round-trip (bulk PATCH) |
| `find_methods` | `plc_ip` | `{"matches": [id, ...]}` | none (cache) |
| `get_method` | `plc_ip`, `method_id` | inArgs/outArgs schema | 1 round-trip |
| `invoke_method` | `plc_ip`, `method_id`, `arguments: {name: value}`, `wait: bool` | `{"status","run_id","out_args"}` if `wait=True`; `{"run_id"}` immediately if `wait=False` | 1+ round-trips |
| `get_method_run` | `plc_ip`, `method_id`, `run_id` | run status - poll until terminal | 1 round-trip |
| `create_watchlist` | `plc_ip`, `parameter_ids: [str]`, `timeout_seconds` | `{"watchlist_id","timeout","parameters":[{id,value,dataType}]}` | 1 round-trip |
| `read_watchlist` | `plc_ip`, `watchlist_id` | current values for all watched params; **resets the inactivity timeout** | 1 round-trip, O(1) regardless of param count |
| `delete_watchlist` | `plc_ip`, `watchlist_id` | `{"status":"ok"}` | 1 round-trip |

### Batching and concurrency rules

- **One parameter × N PLCs** → `get_parameters_bulk`. This is the intended
  fleet-wide pattern and the only one that scales - N concurrent round-trips
  fired in parallel, partial failures don't abort the batch.
- **N parameters × one PLC** → keep batches to **≤8 parameters per call**.
  Larger single-PLC batches have been observed to return 500s even for
  valid parameter IDs - this is a PLC-side limitation, not a client bug.
  Split larger requests into multiple ≤8-sized calls, or switch to a
  watchlist if the read is recurring rather than one-shot.
- **Repeated reads of a fixed set** → watchlist (below), not repeated
  `get_parameter`/`get_parameters_bulk` calls. `read_watchlist` is O(1) per
  call regardless of how many parameters are in the list. This is a hard
  requirement for any polling loop running more than once per minute across
  more than ~3 parameters.

### Error and partial-failure shapes

- Single-item tools (`get_parameter`, `get_method`, `invoke_method`) raise/
  return a top-level `{"error": str}` on failure - check for this key before
  trusting other fields are present.
- Batch tools (`get_parameters_bulk`) **never abort on a single item
  failure** - iterate the full returned list and check each item for an
  `"error"` key rather than assuming uniform success.
- `set_parameters` pre-validates writeability per parameter before sending
  anything to the device. A rejection means the parameter is genuinely
  read-only on that firmware/device-class combination - retrying with a
  different value will not help; don't loop on it.
- `parameter_count_ok` from `describe_plc` is a **floor check**
  (`actual >= expected`), not exact-match. A device reporting *more*
  parameters than the baseline is not an error condition (WDA exposes
  dynamic instance parameters only when configured, and a Yocto-generation
  device on the same hardware line legitimately reports ~3x - see "Device
  generations" above) - only *fewer* than expected indicates a real problem
  (incomplete registration sweep, wrong device-class inference).

### Idempotency and retry guidance

- `get_*` and `find_*` tools are safe to retry freely - no side effects.
- `set_parameters` is safe to retry on transport failure (timeout, connection
  drop) as long as the request didn't already return a definitive
  success/failure - PATCH semantics make re-sending the same value a no-op.
- `invoke_method` is **not assumed idempotent** - check `get_method`'s
  inArgs/outArgs schema and the method's semantics before retrying a method
  call blindly (e.g. retrying a reboot trigger or a firmware-update start is
  not the same as retrying a read).
- For long-running methods, call with `wait=False`, capture `run_id`, and
  poll `get_method_run` rather than blocking on a synchronous wait - this
  matters more for agent pipelines than a chat UI, since a blocked
  synchronous call can stall an entire orchestration step.

## Writing values and triggering actions - be careful, but not paranoid

- `set_parameters` checks ahead of time whether a value is actually
  changeable and will tell you clearly if it isn't - you don't need to guess.
- Every write and every action triggered is logged automatically by the
  server in a tamper-evident audit log. Mention this if asked "how do I know
  what changed" - nothing done here is invisible.
- In a chat UI: if a request is destructive or hard to reverse (rebooting a
  controller, disabling a running service, changing network settings that
  could cut off access, reassigning a physical I/O pin's DI/DO role),
  confirm with the user before doing it - same as for any other irreversible
  action. Read-only lookups never need confirmation.
- Some actions take time (firmware updates, etc.). Use `invoke_method` with
  `wait=False` for those, then `get_method_run` to check progress instead of
  blocking.

### Safety gates you cannot bypass

The server enforces guardrails in code - they are not suggestions:

- **Read-only PLCs** reject `set_parameters` and `invoke_method` outright
  (`{"error": "... read-only ..."}`). Do not retry; the host is deliberately
  frozen. Surface it to the operator instead.
- **Dangerous methods** (IDs containing `reboot`/`restart`/`factory`/`firmware`/
  `format`) are **denied** in live mode unless the operator allowlisted that
  exact ID. Do not try to work around a denial.
- In **GitOps mode** a dangerous method returns `status: proposed` with
  `requires_human: CRITICAL` and an empty `approved_by`. Commit the YAML and
  open the PR, but **never fill `approved_by` yourself** - a human reviewer
  sets it. `apply.py` refuses to run the op until then.
- If you hit a gate, say plainly that the action is blocked for safety and
  who can authorize it - don't try to find a way around it. On a production
  line a badly-timed reboot (or an I/O pin flipped from input to output
  while something is wired to it) can damage equipment or worse, so these
  guardrails are intentional, not a bug to route around.

## GitOps mode - changes go through a pull request

The operator sets this mode with `GITOPS_MODE=1` (Docker) or the **GitOps
mode** checkbox (Claude Desktop extension). **Allow writes and method calls**
must also be on, because a read-only PLC refuses the request before GitOps
mode applies. You cannot switch the mode yourself.

How to recognize it: `set_parameters` and `invoke_method` do not touch the PLC.
They return `status: "proposed"` with `config_file`, a YAML body
(`desired_state_yaml` or `ops_yaml`) and `next_step`.

What to do with the result:

1. Do not retry the write. The PLC did not change, so do not tell the user
   that it changed. Say "proposed, waiting for review".
2. Commit the YAML to the config repository that `next_step` names (default
   `wago-plc-config`). The server does not store the YAML and does not ship
   this repository. It is the operator's own repository.
   - `set_parameters` -> merge the keys into `plcs/<ip>.yaml` under
     `managed_parameters`. Keep the keys that are already there.
   - `invoke_method` -> create `ops/<id>.yaml` with `ops_yaml`. CI deletes it
     after it runs.
3. Open a pull request with a GitHub tool.
   If you cannot write to the repository, give the user the file path and
   the YAML. The user commits it.
4. A person reviews and merges the pull request. CI runs `scripts/apply.py`
   (dry run on the pull request, apply on merge to `main`).
5. After the merge, read the parameter again with `get_parameter` to confirm
   the change.

Never write a value in `approved_by` in an ops file. CI sets it from the
person who approves the pull request.

## Watchlists - efficient repeated checking

Use a watchlist instead of repeated single reads whenever something needs
monitoring over time ("watch this", "let me know if X changes", "poll every
30 seconds", or any agent polling loop):

```
create_watchlist(plc_ip, parameter_ids, timeout_seconds=N)
  → returns watchlist_id immediately, with initial values inline
→ read_watchlist(plc_ip, watchlist_id)   # call on your polling interval
  → resets the timeout on every successful read
→ delete_watchlist(plc_ip, watchlist_id) # explicit cleanup
```

- The watchlist stays alive on the PLC as long as it's read regularly; it
  auto-expires after `timeout_seconds` of inactivity. If your polling
  interval is shorter than `timeout_seconds`, it never expires on its own -
  call `delete_watchlist` explicitly when done, or it leaks server-side
  resources on the PLC until the next process restart.
- If your polling interval might exceed `timeout_seconds` (agent paused,
  rate-limited), set `timeout_seconds` generously - a watchlist that expired
  mid-task means the next `read_watchlist` fails with an unknown-ID error,
  and you must detect that and call `create_watchlist` again.
- `timeout_seconds=0` is a valid one-shot mode: a combined read of multiple
  parameters in a single call, with no server-side state left behind. Good
  for a one-time check of more than ~5 values on one PLC.

## Device-class–aware reasoning

Not all parameters/methods exist on all device classes, and - per the
section above - not even the *shape* of a concept like "DNS" or "I/O
channel" is guaranteed to match across firmware generations. Always check
`describe_plc`'s `features` list or run `find_parameters`/`find_methods`
before assuming a capability exists - don't hardcode parameter IDs across a
fleet without first confirming via `describe_plc` and a live
`find_parameters` call that the target device supports that feature. CC100
units are slower to respond (ARM CPU) - don't assume PFC200/PFC300 response
times apply uniformly across the fleet.

## When something goes wrong

- **"Unable to connect" / timeout** - one of three things: wrong IP, a
  networking/routing problem between here and the device, or the device is
  genuinely offline. Don't assume it's broken after one timeout on a device
  that's normally reachable; a `ConnectTimeout` vs. a `ReadTimeout` is a
  useful distinguishing clue (the latter means the TCP connection succeeded
  but the device never answered - often a slow/loaded device rather than a
  network problem). Some older controllers also take 30+ seconds to
  respond.
- **"Parameter not found"** - use `find_parameters` first; a name that
  worked on one device generation may not exist, or may exist under a
  completely different path, on another (see "Device generations" above).
- **A write is rejected as not writeable** - that setting is read-only on
  this device/firmware; say so plainly rather than retrying with different
  values.
- **Bulk read of many settings from one PLC partially fails** - normal for
  large batches; prefer ≤8-parameter batches from a single PLC, and use
  `get_parameters_bulk` for the "one setting, many PLCs" case instead.

## Keep responses grounded

Always relay what the tools actually returned - values, IDs, error messages
- rather than paraphrasing into something vaguer. If `describe_plc` says a
PLC has 47 features, say 47, don't round it to "around 50." Industrial
control settings are exactly the kind of thing where precision matters more
than smoothness.
