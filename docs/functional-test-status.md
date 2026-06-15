# Functional Test Status & Strategy — wago-plc-mcp-server

> Status as of 2026-06-15.
> Goal: prove the server runs smoothly with **all current WAGO WDA functions**
> across **CC100, PFC200, PFC300, and Edge Controller**.
> No automated suite exists yet — the "Done" entries below are manual,
> single-device verifications. The strategy section optimizes toward a repeatable,
> device-parametrized matrix.

---

## Why the old approach was not enough

The previous plan was mock-heavy and validated against one CC100 plus a dev box.
Mocks replay *our assumption* of a WDA response — they cannot catch the things that
actually break this product in the field:

1. **Device + firmware heterogeneity.** CC100 is a constrained build with a 45 s+
   registration timeout and a small parameter set; the Edge Controller has the largest
   parameter set, the most features, and likely the newest WDX firmware. The same tool
   call can succeed on one and time out, paginate differently, or hit a missing feature
   on another — **and the same model on a different firmware can change WDA response
   shapes** (enum cases, pagination, deprecated flags). The test rack (below) carries
   mixed firmware precisely so this is exercised, not assumed.
2. **WDA surface coverage.** The server wraps only a subset of WDA. "All current WDA
   functions" requires an explicit map of every endpoint → wrapped? → tested how? →
   per-device result, including the endpoints we deliberately don't wrap.
3. **Graceful degradation is per-device.** `plc_manager._cache_resources` treats
   `parameters` + `methods` as essential and `devices`/`features`/`enums`/`param-defs`
   as non-essential. Whether a class trips the non-essential path is a *device fact*,
   not a mock fact.

The optimized approach keeps mocks as the fast pre-check layer and adds a live
**device-conformance matrix** as the source of truth.

---

## Test pyramid (what runs, where, when)

| Layer | Scope | Hardware | Runs in CI? | When |
|------|-------|----------|-------------|------|
| **L0 Unit** ✅ done | pure logic (`enricher`, scoring, env parse, audit chain) | none | ✅ yes | every commit |
| **L1 Contract / cassette** ✅ done | WDAClient replayed against *recorded real* per-device responses | none (cassettes) | ✅ yes | every commit |
| **L2 Auth/middleware integration** | `_AuthMiddleware`, rate limit, ASGI | none | ✅ yes | every commit |
| **L3 Live conformance matrix** | read-only battery parametrized over all 4 classes | all reachable PLCs | ⚠️ nightly / on-demand | pre-release, firmware change |
| **L4 Live mutate suite** | writes + method invocation, gated | **lab devices only** | ❌ manual gate | pre-release |
| **L5 Resilience / soak** | token expiry, reconnect, pagination at scale, concurrency, timeout tuning | lab devices | ❌ on-demand | pre-release, perf work |

L0–L2 give fast regression safety. **L3 is the centerpiece** — it is what proves
"runs smoothly across all controllers." L1 cassettes are recorded *from* L3 runs, so
CI replays real device shapes without needing the hardware online.

---

## L3 — Device conformance matrix (the centerpiece)

A single read-only battery, parametrized over **every physical unit** in the rack, so
the matrix is class × firmware, not just class. Units that are unreachable on a given
run are **skipped, not failed**, so the suite still produces a partial matrix.

### Test rack inventory

15 units on `192.168.42.0/24`, contiguous addressing, mixed firmware — the hardware
backing L3/L4/L5:

| Class | Units | IP range | Reg. timeout | Notes |
|-------|:-----:|----------|:------------:|-------|
| CC100 | 5 | `.110 – .114` | 45 s+ | constrained build, smallest param set, slowest handshake |
| PFC200 | 4 | `.115 – .118` | 15 s | mainstream controller |
| PFC300 | 1 | `.119` | 15 s | newer PFC, single unit — its firmware is a unique data point |
| Edge Controller | 5 | `.120 – .124` | 15 s | largest param set, most features, newest WDX |

Spread units across **as many distinct firmware versions as the rack allows** — the
point of multiple units per class is to surface firmware-specific WDA shape drift.

#### Firmware versioning

CODESYS 3 firmware is `MM.mm.pp (NN)` where **`(NN)` is the authoritative build index** —
track it, not just the dotted version. Newest is **04.09.01 (31)**; recent line:

```
04.09.01 (31)   ← current
04.08.14 / .12 / .09 (30)
04.07.51 / .50 / .03 (29)
04.06.01 (28)
```

Some units also carry extra patch revisions. The matrix keys firmware by `(NN)` plus the
dotted patch, so two units on build 30 with different patches are distinct rows.

#### Class identification (hostname heuristic)

When a unit's class is unknown, its **default hostname is a strong hint** (editable, so
not 100 % — but customers usually keep the factory default). Trailing hex = part of the
MAC:

| Class | Hostname pattern | Example |
|-------|------------------|---------|
| CC100 | `CC100-<hex>` | `CC100-592E6C` |
| PFC200 | `PFC200V3-<hex>` | `PFC200V3-5D7140` |
| PFC300 | `PFC300-<hex>` | `PFC300-68440B` |
| Edge | `EC<model>-<hex>` | `EC752-565BE4` |

CM-0 records the hostname and CM-16 cross-checks it against the configured class.

### Device fixture config (`tests/devices.yaml`)

```yaml
# One entry per physical unit. Credentials come from Docker Secrets / env, never here.
# Missing/unreachable units → skipped. firmware is recorded by CM-0, not trusted from here.
units:
  # CC100 ×5  (.110–.114)
  - { id: cc100-110, class: cc100, ip: "192.168.42.110", timeout: 45, fw_hint: "04.09.01(31)" }
  - { id: cc100-111, class: cc100, ip: "192.168.42.111", timeout: 45, fw_hint: "04.08.14(30)" }
  - { id: cc100-112, class: cc100, ip: "192.168.42.112", timeout: 45, fw_hint: "04.07.50(29)" }
  - { id: cc100-113, class: cc100, ip: "192.168.42.113", timeout: 45, fw_hint: "04.06.01(28)" }
  - { id: cc100-114, class: cc100, ip: "192.168.42.114", timeout: 45, fw_hint: "?" }
  # PFC200 ×4 (.115–.118)
  - { id: pfc200-115, class: pfc200, ip: "192.168.42.115", timeout: 15, fw_hint: "04.09.01(31)" }
  - { id: pfc200-116, class: pfc200, ip: "192.168.42.116", timeout: 15, fw_hint: "04.08.12(30)" }
  - { id: pfc200-117, class: pfc200, ip: "192.168.42.117", timeout: 15, fw_hint: "04.07.03(29)" }
  - { id: pfc200-118, class: pfc200, ip: "192.168.42.118", timeout: 15, fw_hint: "?" }
  # PFC300 ×1 (.119)  — only unit of its class
  - { id: pfc300-119, class: pfc300, ip: "192.168.42.119", timeout: 15, fw_hint: "04.09.01(31)" }
  # Edge ×5    (.120–.124)
  - { id: edge-120, class: edge, ip: "192.168.42.120", timeout: 15, fw_hint: "04.09.01(31)" }
  - { id: edge-121, class: edge, ip: "192.168.42.121", timeout: 15, fw_hint: "04.08.09(30)" }
  - { id: edge-122, class: edge, ip: "192.168.42.122", timeout: 15, fw_hint: "04.07.51(29)" }
  - { id: edge-123, class: edge, ip: "192.168.42.123", timeout: 15, fw_hint: "?" }
  - { id: edge-124, class: edge, ip: "192.168.42.124", timeout: 15, fw_hint: "?" }
# fw_hint is a planning label only — CM-0 records the real (NN) build from the device.

# Per-class expectations the matrix asserts against (min params, expected features, …)
class_profiles:
  cc100:  { expect_min_params: 200, mutate_allowed: false }
  pfc200: { expect_min_params: 400, mutate_allowed: false }
  pfc300: { expect_min_params: 400, mutate_allowed: false }
  edge:   { expect_min_params: 800, mutate_allowed: false }
# Flip mutate_allowed: true only on designated non-production lab units (see L4).
```

```python
@pytest.fixture(params=reachable_units())   # one param per physical unit; skips unreachable
def wda_unit(request) -> UnitUnderTest: ...  # carries class + recorded firmware
```

### CM-0 — Device profile capture (run first, recorded into the matrix)

Every live run begins by recording the device's identity so the matrix is meaningful
and firmware regressions are catchable:

```
CM-0  Capture per device: hostname, order number, firmware version + (NN) build index,
      WDX/WDA version, param count, writeable count, method count, feature count,
      enum count, Bearer-token support (yes/no), registration wall-time.
      → Written to tests/reports/profile-<unit-id>-<date>.json
```

### CM — Read-only battery (run against every class)

```
CM-01  Registration succeeds; ping() returns ok=True
CM-02  list_plcs includes the device IP
CM-03  describe_plc returns non-zero parameter_count and method_count
CM-04  CC100 registers within its 45 s timeout; PFC/Edge within 15 s (no cascade)
CM-05  find_parameters("") returns the alphabetical head; total_in_pool == cached count
CM-06  find_parameters with a known keyword returns substring hits ranked before fuzzy
CM-07  get_parameter on 0-0-identity-ordernumber returns the expected order number
CM-08  get_parameter on a boolean param resolves status=Activated/Deactivated
CM-09  get_parameter on an enum_member param resolves label + enum_name
CM-10  get_parameters_bulk reads the same param from every reachable class in parallel
CM-11  find_methods + get_method returns inArgs/outArgs schema (CC100 may expose fewer)
CM-12  create_watchlist → read_watchlist → delete_watchlist round-trips with live values
CM-13  Pagination: a param set larger than page_limit returns all pages (Edge especially)
CM-14  Graceful degradation: if devices/features/enums absent on a class, PLC still
       registers and describe_plc reflects the zero counts (no crash)
CM-15  Enum resolution matches the device's own enum-definitions (no cross-device bleed)
CM-16  Hostname prefix matches the configured class (CC100-* / PFC200V3-* / PFC300-* /
       EC<model>-*); mismatch → WARN, not fail (hostname is editable), record both in profile
```

### CX — Cross-unit / cross-firmware consistency (the payoff of a real fleet)

These only become possible with multiple units and mixed firmware — they catch the
drift that single-device testing structurally cannot:

```
CX-01  All 5 CC100 register and pass the CM battery regardless of firmware version
CX-02  Within a class, the set of parameter IDs is identical across firmware versions,
       OR every difference is attributable to a deprecated/beta flag (assert, don't ignore)
CX-03  Enum-definition cases for a shared enum are consistent across firmware of one class
CX-04  Bearer-token support is recorded per unit; mixed support within a class is flagged
       (the _token == "" Basic-only path must hold on the non-supporting firmware)
CX-05  A parameter/method ID used in L4 mutate exists on every firmware of its class,
       or the suite resolves a per-firmware equivalent (no hardcoded ID assumptions)
CX-06  Registration wall-time per unit stays within its class budget on every firmware
       (regression guard against a firmware that slows the WDA handshake)
```

### Matrix report artifact

Each run emits `tests/reports/conformance-<date>.md`, one row per **unit** (class +
recorded firmware), so firmware regressions are visible at a glance:

| Unit | Class | FW | CM-01 | CM-09 | CM-11 | CM-13 |
|------|-------|----|:----:|:----:|:----:|:----:|
| cc100-110 | CC100 | 04.09.01(31) | ✅ | ✅ | ⚠️ subset | ✅ |
| cc100-113 | CC100 | 04.06.01(28) | ✅ | ✅ | ⚠️ subset | ✅ |
| pfc300-119 | PFC300 | 04.09.01(31) | ✅ | ✅ | ✅ | ✅ |
| edge-120 | Edge | 04.09.01(31) | ✅ | ✅ | ✅ | ✅ |
| … (15 rows) | | | | | | |

Legend: ✅ pass · ⚠️ pass-with-caveat (expected device limitation) · ❌ fail · ⊘ skipped (unit unreachable).
A class "passes" only when **all reachable units across all firmware** pass.

---

## WDA function coverage matrix — "all current WDA functions"

Every endpoint in `wago-quickref/references/wda-api-reference.md` mapped to its
`WDAClient` method, the MCP tool that surfaces it, the test layer, and per-class
expectation. This is the authoritative answer to "are all WDA functions covered?"

Legend: ✅ wrapped & on the live path · ◐ wrapped but not exposed as an MCP tool ·
❌ **not wrapped (coverage gap)** · N/A not applicable.

| WDA endpoint | WDAClient | MCP tool | Layer | Status |
|--------------|-----------|----------|-------|--------|
| `GET /wda` (identity) | `ping` / `_acquire_token` | — | L3 CM-01 | ✅ |
| `GET /wda/devices` | `list_devices` | describe_plc (count) | L3 | ✅ |
| `GET /wda/devices/{id}` | `get_device` | — | L1 | ◐ |
| `GET /wda/devices/{id}/features` | — | — | — | ❌ gap |
| `GET /wda/parameters` | `list_parameters` | find_parameters | L3 CM-05 | ✅ |
| `GET /wda/parameters/{id}` | `get_parameter` | get_parameter | L3 CM-07 | ✅ |
| `PATCH /wda/parameters` (bulk) | `set_parameters` | set_parameters | L4 | ✅ |
| `PATCH /wda/parameters/{id}` | `set_parameter` | — | L4 | ◐ |
| `GET …/{id}/referencedinstances` | — | — | — | ❌ gap |
| `GET /wda/parameter-definitions` | `list_parameter_definitions` | (writeable cache) | L3 CM-06 | ✅ |
| `GET /wda/parameter-definitions/{id}` | `get_parameter_definition` | — | L1 | ◐ |
| `GET /wda/methods` | `list_methods` | find_methods | L3 CM-11 | ✅ |
| `GET /wda/methods/{id}` | `get_method` | get_method | L3 CM-11 | ✅ |
| `POST /wda/methods/{id}/runs` | `invoke_method` | invoke_method | L4 | ✅ |
| `GET /wda/methods/{id}/runs` (list) | — | — | — | ❌ gap |
| `GET …/runs/{run_id}` | `get_method_run` | get_method_run | L4 | ✅ |
| `DELETE …/runs/{run_id}` | `delete_method_run` | — | L4 | ◐ |
| `GET /wda/method-definitions/{id}/inargs` | `get_method_inargs` | get_method | L3 CM-11 | ✅ |
| `GET …/inargs/{name}` | — | — | — | ❌ gap |
| `GET /wda/method-definitions/{id}/outargs` | `get_method_outargs` | get_method | L3 CM-11 | ✅ |
| `GET …/outargs/{name}` | — | — | — | ❌ gap |
| `GET /wda/features` | `list_features` | describe_plc | L3 | ✅ |
| `GET /wda/features/{id}` | `get_feature` | — | L1 | ◐ |
| `GET …/includedfeatures` | — | — | — | ❌ gap |
| `GET …/containedparameters` | — | — | — | ❌ gap |
| `GET …/containedmethods` | — | — | — | ❌ gap |
| `GET /wda/enum-definitions` | `list_enum_definitions` | (enum cache) | L3 CM-09 | ✅ |
| `GET /wda/enum-definitions/{id}` | `get_enum_definition` | — | L1 | ◐ |
| `POST /wda/monitoring-lists` | `create_monitoring_list` | create_watchlist | L3 CM-12 | ✅ |
| `GET /wda/monitoring-lists` (list) | `list_monitoring_lists` | — | L1 | ◐ |
| `GET /wda/monitoring-lists/{id}` | `get_monitoring_list` | read_watchlist | L3 CM-12 | ✅ |
| `GET …/{id}/parameters` | `read_monitoring_list_parameters` | — | L1 | ◐ |
| `DELETE /wda/monitoring-lists/{id}` | `delete_monitoring_list` | delete_watchlist | L3 CM-12 | ✅ |
| Class instances `…/instances/**` | — | — | — | ❌ gap (read-only per spec) |
| File API `/files/**` | — | — | — | ❌ gap |

**Action items surfaced by this matrix:**
- The ◐ rows (`get_device`, `get_feature`, `get_enum_definition`, `list_monitoring_lists`,
  `read_monitoring_list_parameters`, `set_parameter`, `delete_method_run`,
  `get_parameter_definition`) are reachable in code but have **no test** — cover them at
  L1 with cassettes; cheap and they protect the registration/enrichment path.
- The ❌ gaps are deliberate non-coverage. Decide per gap: *wrap + test* (e.g.
  `method runs list` for audit, class instances for richer devices) or *document as
  out-of-scope* in `SKILL.md` so it's an explicit product decision, not an accident.

---

## L1 — Contract / cassette tests (real shapes, no live hardware in CI)

Record real WDA responses **once per device class** during an L3 run, store them as
cassettes, and replay them in CI with `respx`. This is what lets CI catch
device-shape regressions without the fleet being online.

**L1 status: ✅ done (TT3).** 62 tests in `tests/contract/`. Hand-authored cassettes for
cc100/edge/pfc200 (`tests/cassettes/<class>/`), respx router fixtures, and
`tests/tools/record_cassettes.py` with a unit-tested `scrub()`. CT-02..CT-07 covered
incl. 2-page pagination merge and inArgs `{"value":…}` body assertion. **TT5 must
re-record these from live hardware** — current cassette `_meta.firmware` values are
illustrative and CT-07's stale-guard will enforce the swap. Suite total: 172.

```
CT-01  Record cassettes per class: parameters, parameter-definitions, methods,
       method inargs/outargs, devices, features, enum-definitions, one monitoring-list.
       → tests/cassettes/<class>/*.json   (scrub serials/credentials on capture)
CT-02  _cache_resources against each cassette → ID sets, param_path, param_writeable,
       param_user_setting, param_to_enum, enum_cases populated as expected
CT-03  CC100 cassette with empty/absent features → registers, features set = ∅ (CM-14 in CI)
CT-04  Edge cassette with multi-page parameters → _paginate walks every links.next
CT-05  enrich_parameter against a real enum_member attrs blob → correct label
CT-06  Replay invoke_method run response (done / progress / error) → correct tool output
CT-07  Re-record guard: a cassette older than firmware in CM-0 profile fails with a
       "stale cassette — re-record from <class>" message
```

---

## L4 — Live mutate suite (writes + methods, gated to lab devices)

**Never runs in CI. Never against production.** Gated behind `--run-mutate` + a
`devices.yaml` flag `mutate_allowed: true` per device.

```
MW-01  set_parameters on a known-safe writeable param (e.g. a user-setting label),
       read back, assert new value, then restore original (snapshot/rollback pattern)
MW-02  set_parameters PATCH returns 204/empty → tool returns {"status":"ok"}
MW-03  set_parameters on a read-only param → blocked by cache pre-check (no PLC call)
MW-04  set_parameters with unknown id → blocked by cache pre-check
MW-05  Bulk set with one bad sibling → WDA error_code 41 surfaced, audit row = error
MW-06  invoke_method idempotent/safe method (e.g. ntpclient-updatetime) wait=True → done
MW-07  invoke_method wait=False → run_id returned; get_method_run polls to done
MW-08  invoke_method missing required arg → WDA error_code 22 surfaced cleanly
MW-09  invoke_method wrong value type → error_code 24 surfaced cleanly
MW-10  Every MW write produces a hash-chained audit entry (verify prev linkage)
```

Run the mutate suite on **each class that has a lab unit** — method/parameter IDs and
availability differ across CC100/PFC/Edge, so MW-06's safe method must be resolved per
device, not hardcoded.

---

## L5 — Resilience / soak

```
RS-01  Token expiry: force WDA token past WAGO-WDX-Auth-Token-Expiration → next request
       transparently re-auths (log shows refresh), no tool-level error
RS-02  Token corruption: inject 401 on a Bearer request → single re-auth → success (L1 mock + L5 live)
RS-03  Bearer-not-supported class: _token == "" path stays on Basic Auth indefinitely
RS-04  Concurrent first requests (cold _token): only one _acquire_token fires (lock)
RS-05  Registration cascade: all classes at once under semaphore=5 → no ReadTimeout storm
RS-06  CC100 under its 45 s timeout while PFCs finish fast → no class starves another
RS-07  Pagination at scale: Edge full parameter list (multi-page) completes < N s
RS-08  Watchlist timeout: create with timeout=5, wait, read → expired handled cleanly
RS-09  PLC goes unreachable mid-session → tool returns error, server stays up, other PLCs fine
RS-10  Long soak (1 h): periodic reads across fleet, assert no token/handle/memory leak
```

---

## L0 — Unit & L2 — Middleware (fast pre-check, condensed)

These stay valuable as the sub-second regression net. Full case list retained from the
prior revision; essentials:

```
UT  enrich_parameter (bool/enum/writeable), parse_watchlist_response, enrich_method_definition
UT  _score / _filter_search (exact>prefix>substring>fuzzy, limit cap)
UT  _parse_plcs_from_env fallback order (per-PLC secret > per-PLC env > shared secret > env > "wago")
UT  _check_key_entropy (<32 → SystemExit), _audit_log JSON + prev-hash, _seed_audit_hash (seed/missing/non-JSON)
IT  _AuthMiddleware: /health exempt, /mcp 401 without/with-wrong key, 200 with key, dev-mode passthrough
IT  rate limit 60/min → 429 + Retry-After; per-IP buckets; failure counter → ALERT at 10; reset on success
```

**L0 status: ✅ done (TT1).** 82 tests in `tests/unit/` — `enricher.py` 100 %, targeted
`main.py` helpers 100 % (115/115).
**L2 status: ✅ done (TT2).** 28 tests in `tests/unit/test_auth_middleware.py` —
`_AuthMiddleware` health-exempt / 401 / pass-through / dev-mode / rate-limit (429 +
Retry-After, per-IP buckets, window reset) / auth-failure ERROR alert. Suite total: 110.

---

## Data-type & WDA error-code conformance

Two cross-cutting batteries that ride on L1 (mock) + L3/L4 (live) — they protect the
shapes the CLAUDE.md calls out as "the shapes that bite."

```
DT-01  uint64 param → stringValue preserved (no JS precision loss) on read and set
DT-02  enum_member → integer in, label out
DT-03  boolean → status field; float32/64 → number; bytes → base64 round-trip
DT-04  invoke_method inArg wrapped as {"value": ...}, never flat (assert request body)

EC-01  Map each WDA error_code we can provoke to a clean tool error:
       17 unknown_parameter_path · 19 not_a_method · 20 wrong_argument_count ·
       21 could_not_set_parameter · 22 missing_argument · 24 wrong_value_type ·
       26 could_not_invoke_method · 31 parameter_not_writeable · 41 other_invalid_value_in_set
EC-02  error_code is surfaced (more specific than HTTP status) in the tool response
EC-03  426 (HTTP-not-HTTPS) and 503 (WDA down) produce the right ping() reason per CM-01
```

**Status: ✅ done (TT4)** — 60 tests in `tests/contract/test_datatypes.py` +
`test_error_codes.py`. DT-01..04 and client-level EC (real `WDAClient` raising on all 9
codes) are genuine. ⚠️ **Caveat:** the EC *tool-layer* mapping is verified via a
reimplemented stub, not the real `main.py` tools — see **TT4-FU** in
`test-implementation-todos.md` for the deferred fix. Suite total: 232.

---

## Tooling & how to run

```
pytest                 # runner
pytest-asyncio         # async (all WDAClient + tool tests)
respx                  # httpx mock + cassette replay (L1)
httpx[asgi]            # ASGI TestClient for _AuthMiddleware (L2)
pytest-cov             # coverage gate, target ≥ 80% on src/ for L0–L2
pyyaml                 # devices.yaml fixture config
```

```bash
# Bring up the dev image (test harness lives here; prod image has no tests/):
docker rm -f wmcp && docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build

# Fast lane — every commit, no hardware (L0–L2 + L1 cassettes)
docker exec wmcp pytest tests/ -m "not live and not mutate" --cov=src --cov-report=term-missing

# Live read-only conformance matrix across all reachable classes (L3)
docker exec wmcp pytest tests/ -m live --device-config tests/devices.yaml

# Mutate suite — lab only, explicit opt-in (L4)
docker exec wmcp pytest tests/ -m "live and mutate" --run-mutate --device-config tests/devices.yaml

# Resilience / soak (L5)
docker exec wmcp pytest tests/ -m soak --device-config tests/devices.yaml
```

Markers: `live` (needs a PLC), `mutate` (writes), `soak` (long), parametrized over
device class. Absent classes auto-skip. Ship `tests/` only in a `dev` Docker target.

### Recommended sequencing to reach confidence

1. **L0 + L2** — pure logic + middleware. No hardware. (≈ 1 day)
2. **L1 cassettes** — record once from each available class, replay in CI. Captures real
   device shapes; this is the highest-leverage step after units. (≈ 1–2 days incl. capture)
3. **L3 live matrix** — run against the full 15-unit rack (one row per unit + firmware),
   publish the conformance + coverage + cross-firmware (CX) matrices. This is the "runs
   smoothly across all controllers and firmware" evidence. (≈ 1–2 days with the rack)
4. **L4 mutate** on lab units, then **L5 soak** before each release.

---

## Done — already verified (manual, single-device baseline)

These were ad-hoc manual checks on a CC100 + dev box during CRA hardening. The
optimization above promotes them from one-off manual runs to the repeatable,
all-class matrix (L3/L4). Kept here as the historical baseline.

**Container / transport:** `/mcp` initialize ✅ · streamable-http default ✅ · sse fallback ✅ · `/health` unauth 200 ✅
**Auth (T1):** no-header 401 ✅ · wrong-key 401 ✅ · correct-key OK ✅ · `/health` exempt ✅ · auto-keygen once ✅ · key persisted across restart ✅ · short-key startup abort ✅
**Secrets (T2):** secret mounted ✅ · PLCs register via secret ✅ · env fallback ✅ · factory-default warning ✅
**WDA Bearer (T3):** token acquired ✅ · subsequent Bearer ✅ · 16-PLC fleet no regression ✅
**Audit (T4):** set_parameters JSON entry ✅ · invoke_method entry ✅ · separate files ✅ · prev-hash chain ✅ · seed-on-restart ✅
**TLS / SBOM:** WDA TLS-off warning ✅ · MCP TLS-off warning ✅ · syft SBOM on build ✅ · `--release` archive ✅ · syft-absent WARNING-not-fail ✅
**MCP tools happy-path (single CC100):** all 13 tools exercised except `get_method_run` (not yet run live).

Gap vs. optimized target: every ✅ above was **one device, one firmware**. Re-run as the
parametrized L3/L4 matrix across the 15-unit rack (5 CC100 · 4 PFC200 · 1 PFC300 ·
5 Edge, mixed firmware) to claim coverage across all classes *and* firmware versions.
