# Test Implementation ToDos — wago-plc-mcp-server

> Work briefings for building the functional test suite. **Spec:** `docs/functional-test-status.md`
> (layers L0–L5, conformance matrix CM/CX, coverage matrix). Each task below is
> self-contained — a fresh agent can pick up any one from its last checked box.
>
> **Hard rules (do not violate):**
> - **Run everything in Docker.** Never `pip install`/`pytest` on the host. The test
>   harness lives in the **dev** image (built via `docker-compose.dev.yml`); a plain
>   `docker compose up` builds the production image and has **no** `tests/`. Cycle:
>   `docker rm -f wmcp && docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build`
>   then `docker exec wmcp pytest tests/ ...`.
> - **Never read or print credentials.** `.env`, `_env`, `secrets/` are off-limits to
>   `cat`. Test creds come from Docker Secrets / env at runtime.
> - **Mock `httpx` at the `WDAClient` boundary** for non-live tests (use `respx`).
> - **WDA payload shapes are authoritative in** `wago-quickref/references/wda-api-reference.md`.
> - Ship `tests/` only in a **dev** Docker build target, never the production image.
> - Conventional commits, feature branch (`test/...`), show diff before committing.

---

## TT0 — Test scaffolding & tooling (do first)

### Goal
Stand up the pytest harness in-container so every later task has somewhere to land.

### Deliverables
- `tests/` package with `conftest.py`, `tests/unit/`, `tests/contract/`, `tests/live/`.
- `pyproject.toml`: add dev deps `pytest`, `pytest-asyncio`, `respx`, `httpx[asgi]`,
  `pytest-cov`, `pyyaml`. Configure `[tool.pytest.ini_options]` with markers:
  `live`, `mutate`, `soak` and `asyncio_mode = "auto"`.
- Dockerfile: a `dev` target (or build arg) that installs dev deps + copies `tests/`.
  Production image must stay unchanged (no tests, no dev deps).
- `tests/devices.yaml` exactly as specified in `functional-test-status.md` (15 units,
  IPs `.110–.124`, classes, `fw_hint`, `class_profiles`). Fill `fw_hint: "?"` where unknown.

### Checkpoints
- [ ] `docker exec wmcp pytest tests/ -q` runs and collects 0 tests without error
- [ ] `docker exec wmcp pytest -m "not live and not mutate and not soak"` selects cleanly
- [ ] Production image build does **not** contain `tests/` (`docker run ... ls` proves it)
- [ ] Marker config present; `pytest --markers` lists live/mutate/soak

---

## TT1 — L0 unit tests (pure logic, no network)

### Goal
Cover `enricher.py` and the pure helpers in `main.py`. Target ≥ 80 % on those modules.

### Targets & cases (see L0 block in spec)
- `enricher.py`: `enrich_parameter` (boolean status, enum_member label+enum_name, unknown
  enum value, writeable flag), `parse_watchlist_response` (included params, empty, error
  attr), `enrich_method_definition` (inArgs/outArgs inlined).
- `main.py` helpers: `_score`, `_filter_search` (ranking + fuzzy fallback + limit cap),
  `_parse_plcs_from_env` (full fallback order), `_check_key_entropy` (<32 → SystemExit),
  `_audit_log` (valid JSON + prev-hash linkage), `_seed_audit_hash` (seed / missing /
  non-JSON tail).

### Notes
- `_parse_plcs_from_env` reads env + `/run/secrets/*`. Use `monkeypatch` for env and a
  `tmp_path` shimmed secrets dir (patch the `Path("/run/secrets")` lookups) — never touch
  the real `secrets/`.
- `_audit_log` mutates a module global `_AUDIT_PREV_HASH`; reset it between tests.

### Checkpoints
- [ ] `docker exec wmcp pytest tests/unit -v` green
- [ ] `--cov=src/enricher --cov=src/main` reports ≥ 80 % on the covered helpers
- [ ] Audit chain test asserts `sha256(line[n]) == entry[n+1]["prev"]`

---

## TT2 — L2 auth & middleware integration (ASGI, no PLC)

### Goal
Test `_AuthMiddleware` end-to-end with an ASGI transport, no PLC needed.

### Cases (see L2 / IT block)
- `/health` exempt (200 with and without auth header).
- `/mcp` → 401 without header, 401 wrong Bearer, pass-through with correct key.
- Dev mode (`api_key=""`) → all traffic forwarded.
- Rate limit: 60/min ok, 61st → 429 + `Retry-After`; per-IP buckets independent; window reset.
- Auth-failure counter → ERROR alert at 10; reset on success.

### Notes
- Wrap `_AuthMiddleware` around a trivial inner ASGI app that echoes 200, then drive it
  with `httpx.AsyncClient(transport=httpx.ASGITransport(app=...))`.
- Rate-limit + failure state are per-instance dicts — construct a fresh middleware per test.
- `time.monotonic()` drives the window; monkeypatch it to test expiry deterministically.

### Checkpoints
- [ ] `docker exec wmcp pytest tests/unit/test_auth_middleware.py -v` green
- [ ] 429 path asserts the `retry-after` header
- [ ] Alert test asserts the ERROR log line at the 10th failure

---

## TT3 — L1 contract / cassette tests (real shapes, replayed)

### Goal
Replay **recorded real WDA responses** through `WDAClient` + `_cache_resources` with no
live hardware, so CI catches device-shape regressions. Depends on first-light L3 (TT5) to
record cassettes — until then, hand-author minimal cassettes from the reference payloads.

### Deliverables
- `tests/cassettes/<class>/*.json` for: parameters, parameter-definitions, methods,
  method inargs/outargs, devices, features, enum-definitions, one monitoring-list.
- A `respx` fixture that maps `https://<ip>/wda/...` routes to the cassette files.
- A capture helper (`tests/tools/record_cassettes.py`) usable during TT5 to dump live
  responses, **scrubbing serials/order-numbers/tokens** on the way out.

### Cases (see L1 / CT block)
- `_cache_resources` populates ID sets + `param_path` + `param_writeable` +
  `param_user_setting` + `param_to_enum` + `enum_cases` as expected per class.
- CC100 cassette with empty/absent features → registers, `features == ∅` (CM-14 in CI).
- Edge multi-page parameters → `_paginate` walks every `links.next`.
- `enrich_parameter` on a real `enum_member` blob → correct label.
- invoke_method run response replay (done / progress / error) → correct tool output.
- Stale-cassette guard: cassette older than CM-0 firmware → fails with re-record message.

### Checkpoints
- [ ] `docker exec wmcp pytest tests/contract -v` green with hand-authored cassettes
- [ ] Pagination test uses a 2-page cassette and asserts both pages merged
- [ ] Capture helper scrubs secrets (unit-test the scrubber on a sample blob)

---

## TT4 — L0/L1 data-type & WDA error-code conformance

### Goal
Lock down the "shapes that bite" (CLAUDE.md) at mock level; live re-runs ride on TT5–TT6.

### Cases (see DT / EC blocks)
- DT: uint64 `stringValue` preserved on read+set; enum_member int-in/label-out; boolean
  status; float; bytes base64 round-trip; invoke_method inArg wrapped `{"value": ...}`
  (assert the **request body** respx received).
- EC: provoke and map WDA `error_code`s 17/19/20/21/22/24/26/31/41 → clean tool errors;
  assert `error_code` surfaced (more specific than HTTP status); 426/503 → right `ping()`
  reason.

### Checkpoints
- [x] `docker exec wmcp pytest tests/contract/test_datatypes.py tests/contract/test_error_codes.py -v` green
- [x] inArg-wrapping test inspects the captured PATCH/POST JSON, not just the return value

### Follow-up (deferred tech debt — TT4-FU)
The EC **tool-layer** mapping is currently verified via `_apply_tool_wrapper()`, a
reimplemented copy of `main.py`'s `except Exception → {"error": str(e)}` block — not the
real tool functions. This was a wrong call (the agent assumed importing `main` / calling
the decorated tools was infeasible; both are fine — `@mcp.tool()` returns the function
unchanged and `main` imports cleanly, as TT1 already does). DT tests and the
**client-level** EC tests (real `WDAClient` raising on each code) are genuine.
**To do:** rewrite the EC tool-level assertions to call the real
`main.set_parameters` / `main.invoke_method` / `main.get_parameter` against a
respx-registered fake PLC (reuse TT5/TT3 register flow) + a dummy `Context`, and drop the
stub. Until then, regressions in the actual tool error-mapping are not caught.

---

## TT5 — L3 live conformance matrix (the centerpiece)

### Goal
Run the read-only battery (CM-0, CM-01–16) parametrized over **every reachable unit** in
the rack, emit the per-unit report, and record cassettes for TT3.

### Deliverables
- `reachable_units()` helper: load `devices.yaml`, ping each, return only responsive units;
  unreachable → `pytest.skip` (never fail).
- `wda_unit` fixture (param per physical unit, carries class + CM-0 recorded firmware).
- `tests/reports/conformance-<date>.md` (one row per unit: class + FW + CM results) and
  `tests/reports/profile-<unit-id>-<date>.json`.
- Trigger `record_cassettes.py` during the run to feed TT3.

### Cases
All CM-0 / CM-01..CM-16 from the spec. Per-class expectations come from
`class_profiles` (e.g. `expect_min_params`). CM-16 = hostname-prefix vs class
(`CC100-*` / `PFC200V3-*` / `PFC300-*` / `EC<model>-*`), WARN not fail.

### How to run
```bash
docker exec wmcp pytest tests/live -m live --device-config tests/devices.yaml
```

### Checkpoints
- [ ] All reachable units register and pass CM-01..CM-03
- [ ] CC100 units register within 45 s; PFC/Edge within 15 s (CM-04)
- [ ] Report artifact written with one row per reachable unit
- [ ] Profiles capture firmware `(NN)` build + hostname for every unit
- [ ] Cassettes recorded (secrets scrubbed) for at least one unit per class

---

## TT6 — L3 cross-unit / cross-firmware consistency (CX)

### Goal
Exploit the fleet: assert consistency across units of a class and across firmware builds.

### Cases (CX-01..CX-06 in spec)
- All 5 CC100 pass CM regardless of FW.
- Within a class, parameter-ID sets identical across FW, OR every diff maps to a
  deprecated/beta flag (assert the flag, don't silently ignore).
- Enum cases for a shared enum consistent across a class's firmware.
- Bearer support recorded per unit; mixed support within a class flagged.
- Mutate IDs (for TT7) exist on every FW of their class, else per-FW equivalent resolved.
- Registration wall-time within class budget on every FW (regression guard).

### Notes
- These consume the TT5 profiles/cassettes; structure as a session-scoped collection over
  all units of a class. PFC300 has **one** unit — CX checks that need ≥2 units must
  `skip` for PFC300 with a clear reason (single sample, can't triangulate).

### Checkpoints
- [ ] `docker exec wmcp pytest tests/live -m live -k cross -v`
- [ ] Param-ID diff across CC100 firmware is either empty or fully flag-attributed
- [ ] PFC300-only CX checks skip with an explicit single-unit reason

---

## TT7 — L4 mutate suite + L5 resilience/soak (lab-gated)

### Goal
Cover writes, method invocation, and resilience — **gated, never in CI, never production.**

### Gating
- Runs only with `--run-mutate` AND `class_profiles.<class>.mutate_allowed: true`.
- Flip `mutate_allowed` only on designated non-production lab units.

### Cases
- **L4 (MW-01..MW-10):** safe writeable-param round-trip with snapshot/rollback; 204→ok;
  read-only & unknown blocked by cache pre-check; bad-sibling bulk → error_code 41;
  safe method (resolved per FW, e.g. `ntpclient-updatetime`) sync + async; missing arg
  (22) / wrong type (24) surfaced; every write produces a hash-chained audit entry.
- **L5 (RS-01..RS-10):** token expiry → transparent re-auth; token corruption → single
  re-auth; Basic-only (`_token == ""`) path; concurrent cold-token → one `_acquire_token`
  (lock); registration cascade under semaphore=5 (all 15 at once) no ReadTimeout storm;
  CC100 45 s vs PFC fast no starvation; Edge multi-page pagination time bound; watchlist
  timeout expiry; PLC unreachable mid-session → tool errors, server survives, peers fine;
  1 h soak → no token/handle/memory leak.

### How to run
```bash
docker exec wmcp pytest tests/live -m "live and mutate" --run-mutate --device-config tests/devices.yaml
docker exec wmcp pytest tests/live -m soak --device-config tests/devices.yaml
```

### Checkpoints
- [ ] Every MW write restores original value (rollback verified by re-read)
- [ ] Audit entries for mutate ops form an unbroken hash chain
- [ ] RS-05 starts all 15 units concurrently with no ReadTimeout cascade
- [ ] Soak run reports stable memory + no leaked client handles

---

## Suggested order & branches

```
TT0 → TT1 → TT2 → (TT3 hand-authored) → TT4   [all CI-safe, no hardware]
        ↓
TT5 (live, records cassettes) → backfill TT3 cassettes → TT6
        ↓
TT7 (lab-gated)
```

Branch per task: `test/tt0-scaffold`, `test/tt1-unit`, … Keep `tests/` out of the prod image.
Update `docs/functional-test-status.md` "Done" section as each layer lands.
