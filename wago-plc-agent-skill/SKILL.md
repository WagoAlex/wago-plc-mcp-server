---
name: wago-plc-agent
description: |
  Use when an autonomous agent (not a human in a chat UI) needs to call the
  WAGO PLC MCP server's tools programmatically — orchestration pipelines,
  monitoring daemons, multi-agent systems, scheduled jobs, or any caller
  that consumes tool output as structured data rather than reading prose.
  Covers call-sequencing rules, batching/concurrency limits, error and
  partial-failure shapes, retry/idempotency guidance, and watchlist
  lifecycle management. Does not cover the underlying WDA REST/HTTP
  protocol (see wago-quickref/SKILL.md for that) — this is the MCP
  tool-contract layer only.
---

# WAGO PLC MCP Server — Agent Integration Contract

This skill documents the **tool-call contract**: inputs, outputs, error
shapes, and sequencing rules for driving this MCP server programmatically.
It does not cover WDA/REST internals — agents calling these tools never see
raw WDA HTTP responses, only the shapes below.

## Canonical call sequence

```
list_plcs
  → describe_plc(plc_ip)                       # cheap, cached — call before assuming capabilities
    → find_parameters / find_methods            # resolve human/fuzzy queries to exact IDs
      → get_parameter / get_method               # inspect before acting
        → set_parameters / invoke_method          # act
          → get_method_run                         # poll if invoked with wait=False
```

Do not skip `describe_plc` before reasoning about what a PLC supports —
`device_class`, `feature_count`, and `parameter_count_ok` are cheap
(cached, no network round-trip) and prevent wasted calls against parameters
or methods that don't exist on that device class.

For repeated reads of a fixed parameter set, replace the
`get_parameter`-in-a-loop pattern with watchlists (see below) — this is a
hard requirement for any polling loop running more than once per minute
across more than ~3 parameters.

## Tool reference — I/O contract

| Tool | Required args | Returns | Network cost |
|---|---|---|---|
| `list_plcs` | — | `{"plcs": [ip, ...]}` | none (cache) |
| `describe_plc` | `plc_ip` | counts + `device_class`, `expected_parameter_count`, `parameter_count_ok` (floor check, not exact match — see below), `features: [str]` | none (cache) |
| `find_parameters` | `plc_ip` | `{"matches": [id, ...], "total_in_pool": int, "truncated": bool}` | none (cache) |
| `get_parameter` | `plc_ip`, `parameter_id` | `{"value", "dataType", "dataRank", "path", "writeable"}` | 1 round-trip |
| `get_parameters_bulk` | `requests: [{"plc_ip","parameter_id"}, ...]` | list of enriched dicts; per-item failures are `{"plc_ip","parameter_id","error"}` and do **not** abort the batch | N concurrent round-trips |
| `set_parameters` | `plc_ip`, `parameters: [{"parameter_id","value"}, ...]` | per-parameter status; pre-validates writeability before sending | 1 round-trip (bulk PATCH) |
| `find_methods` | `plc_ip` | `{"matches": [id, ...]}` | none (cache) |
| `get_method` | `plc_ip`, `method_id` | inArgs/outArgs schema | 1 round-trip |
| `invoke_method` | `plc_ip`, `method_id`, `arguments: {name: value}`, `wait: bool` | `{"status","run_id","out_args"}` if `wait=True`; `{"run_id"}` immediately if `wait=False` | 1+ round-trips |
| `get_method_run` | `plc_ip`, `method_id`, `run_id` | run status — poll until terminal | 1 round-trip |
| `create_watchlist` | `plc_ip`, `parameter_ids: [str]`, `timeout_seconds` | `{"watchlist_id","timeout","parameters":[{id,value,dataType}]}` | 1 round-trip |
| `read_watchlist` | `plc_ip`, `watchlist_id` | current values for all watched params; **resets the inactivity timeout** | 1 round-trip, O(1) regardless of param count |
| `delete_watchlist` | `plc_ip`, `watchlist_id` | `{"status":"ok"}` | 1 round-trip |

## Batching and concurrency rules

- **One parameter × N PLCs** → `get_parameters_bulk`. This is the intended
  fleet-wide pattern and the only one that scales — N concurrent round-trips
  fired in parallel, partial failures don't abort the batch.
- **N parameters × one PLC** → keep batches to **≤8 parameters per call**.
  Larger single-PLC batches have been observed to return 500s even for
  valid parameter IDs — this is a PLC-side limitation, not a client bug.
  Split larger requests into multiple ≤8-sized calls, or switch to a
  watchlist if the read is recurring rather than one-shot.
- **Repeated reads of a fixed set** → watchlist, not repeated
  `get_parameter`/`get_parameters_bulk` calls. `read_watchlist` is O(1) per
  call regardless of how many parameters are in the list; repeated direct
  reads re-pay per-parameter connection overhead every time.

## Error and partial-failure shapes

- Single-item tools (`get_parameter`, `get_method`, `invoke_method`) raise/
  return a top-level `{"error": str}` on failure — check for this key before
  trusting other fields are present.
- Batch tools (`get_parameters_bulk`) **never abort on a single item
  failure** — iterate the full returned list and check each item for an
  `"error"` key rather than assuming uniform success.
- `set_parameters` pre-validates writeability per parameter before sending
  anything to the device. A rejection means the parameter is genuinely
  read-only on that firmware/device-class combination — retrying with a
  different value will not help; don't loop on it.
- `parameter_count_ok` from `describe_plc` is a **floor check**
  (`actual >= expected`), not exact-match. A device reporting *more*
  parameters than the baseline is not an error condition (WDA exposes
  dynamic instance parameters, e.g. SNMP community entries, only when
  configured) — only *fewer* than expected indicates a real problem
  (incomplete registration sweep, wrong device-class inference).

## Idempotency and retry guidance

- `get_*` and `find_*` tools are safe to retry freely — no side effects.
- `set_parameters` is safe to retry on transport failure (timeout, connection
  drop) as long as the request didn't already return a definitive
  success/failure — PATCH semantics make re-sending the same value a no-op.
- `invoke_method` is **not assumed idempotent** — check `get_method`'s
  inArgs/outArgs schema and the method's semantics before retrying a method
  call blindly (e.g. retrying a reboot trigger or a firmware-update start is
  not the same as retrying a read).
- For long-running methods, call with `wait=False`, capture `run_id`, and
  poll `get_method_run` rather than blocking the calling agent's execution
  thread on a synchronous wait — this matters more for agent pipelines than
  for a chat UI, since a blocked synchronous call can stall an entire
  orchestration step.

## Watchlist lifecycle

```
create_watchlist(plc_ip, parameter_ids, timeout_seconds=N)
  → returns watchlist_id immediately, with initial values inline
→ read_watchlist(plc_ip, watchlist_id)   # call on your polling interval
  → resets the timeout on every successful read
→ delete_watchlist(plc_ip, watchlist_id) # explicit cleanup
```

- If your polling interval is shorter than `timeout_seconds`, the watchlist
  never expires on its own — you must call `delete_watchlist` explicitly
  when the monitoring task ends, or it leaks server-side resources on the
  PLC until the next process restart.
- If your polling interval might exceed `timeout_seconds` (e.g. the agent
  could be paused or rate-limited), set `timeout_seconds` generously rather
  than relying on tight timing — a watchlist that expired mid-task means the
  next `read_watchlist` call will fail with an unknown-ID error, requiring
  you to detect that and call `create_watchlist` again.
- `timeout_seconds=0` is a valid one-shot mode: combined read of multiple
  parameters in a single call without leaving server-side state behind.

## Device-class–aware reasoning

Not all parameters/methods exist on all device classes. Always check
`describe_plc`'s `features` list or run `find_parameters`/`find_methods`
before assuming a capability exists — don't hardcode parameter IDs across a
fleet without first confirming via `describe_plc` that the target device
class supports that feature. CC100 units in particular are slower to
respond (ARM CPU) — don't tune aggressive timeouts assuming PFC200/PFC300
response times apply uniformly across the fleet.
