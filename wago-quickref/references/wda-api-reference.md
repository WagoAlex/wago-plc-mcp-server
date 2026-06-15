# WAGO WDA REST API Reference (v1.4.1)

> Load this file only when you need direct HTTP access to the PLC — e.g. for endpoints the `wago-plc-mcp` server doesn't expose, for debugging, or for low-level inspection. For normal operations, use the MCP tools described in the parent `SKILL.md`.
>
> In this document, `<plc_ip>` is a placeholder for an actual PLC IP address, and `<user>:<pass>` is a placeholder for credentials. WAGO's factory-default credentials are `admin:wago` — replace with real ones in production.

## Connection

- Protocol: **HTTPS only** (HTTP returns 426 Upgrade Required)
- Auth: HTTP Basic (`Authorization: Basic <base64(user:pass)>`) or Bearer token
- Content-Type for request bodies: `application/vnd.api+json`
- Accept header (recommended): `application/vnd.api+json`
- Self-signed certs are common — disable verification: `curl -k`, `httpx(verify=False)`

```bash
curl -k -u <user>:<pass> https://<plc_ip>/wda
```

## HTTP status codes that matter

| Code | Meaning |
|---|---|
| 200 | OK with body |
| 201 | Created (e.g. method run, monitoring list) |
| 202 | Accepted (deferred parameter writes) |
| 204 | OK without body (typical for successful PATCH) |
| 400 | Bad request — check `errors[].source.pointer` in body |
| 401 | Not authenticated |
| 404 | Resource not found |
| 405 | Method Not Allowed — wrong HTTP verb on endpoint |
| 406 | Wrong Accept header |
| 415 | Wrong Content-Type |
| 426 | HTTPS required |
| 500 | Server error (often parameter-specific, see body) |
| 503 | WDA service installed but not running |

## All endpoints at a glance

### Service identity (entry point)

```
GET    /wda                                          → service identity + links
```

### Devices

```
GET    /wda/devices                                  → list (paginated)
GET    /wda/devices/{device_id}                      → single device
GET    /wda/devices/{device_id}/features             → features on this device
```

### Parameters

```
GET    /wda/parameters                               → list (paginated, filterable)
GET    /wda/parameters/{parameter_id}                → single value + attributes
PATCH  /wda/parameters                               → bulk write
PATCH  /wda/parameters/{parameter_id}                → single write
GET    /wda/parameters/{parameter_id}/referencedinstances → for instance_identity_ref types

GET    /wda/parameter-definitions                    → all parameter definitions
GET    /wda/parameter-definitions/{id}               → single definition (writeable, userSetting, enum link)
```

### Methods

```
GET    /wda/methods                                  → list (paginated, filterable)
GET    /wda/methods/{method_id}                      → single method
POST   /wda/methods/{method_id}/runs                 → invoke
GET    /wda/methods/{method_id}/runs                 → list past runs
GET    /wda/methods/{method_id}/runs/{run_id}        → poll run status
DELETE /wda/methods/{method_id}/runs/{run_id}        → free server-side run result

GET    /wda/method-definitions                       → list method signatures
GET    /wda/method-definitions/{id}                  → single signature
GET    /wda/method-definitions/{id}/inargs           → in-argument definitions
GET    /wda/method-definitions/{id}/inargs/{name}    → single in-arg
GET    /wda/method-definitions/{id}/outargs          → out-argument definitions
GET    /wda/method-definitions/{id}/outargs/{name}   → single out-arg
```

### Features

```
GET    /wda/features                                 → list of features
GET    /wda/features/{feature_id}                    → single feature
GET    /wda/features/{feature_id}/includedfeatures   → nested features
GET    /wda/features/{feature_id}/containedparameters → param definitions in feature
GET    /wda/features/{feature_id}/containedmethods   → method definitions in feature
```

### Enums

```
GET    /wda/enum-definitions                         → all enums on device
GET    /wda/enum-definitions/{enum_id}               → single enum with cases[]
```

### Monitoring lists (watchlists)

```
POST   /wda/monitoring-lists                         → create, body has parameters
GET    /wda/monitoring-lists                         → list active
GET    /wda/monitoring-lists/{id}                    → metadata (add ?include=parameters for values)
GET    /wda/monitoring-lists/{id}/parameters         → just the values
DELETE /wda/monitoring-lists/{id}                    → cleanup
```

### Class instances (advanced)

```
GET    /wda/parameters/{id}/instances                → instances of a class parameter
GET    /wda/parameters/{id}/instances/{no}           → single instance
GET    /wda/parameters/{id}/instances/{no}/device    → device of instance
GET    /wda/parameters/{id}/instances/{no}/parameters → params of instance
GET    /wda/parameters/{id}/instances/{no}/methods   → methods of instance
```

### File API

```
POST   /files?context=<parameter-id>                 → create new file ID for upload
HEAD   /files/{file_id}                              → file metadata
GET    /files/{file_id}                              → download (supports Range)
PUT    /files/{file_id}                              → upload whole
PATCH  /files/{file_id}                              → upload chunk-wise (multipart/byteranges)
```

## Query parameters worth knowing

- `page[limit]=N` — items per page (default 255, max model-dependent)
- `page[offset]=M` — start index
- `filter[device]=0-0` — filter by device (or use literal `headstation`)
- `filter[path]=NTPClient/Server` — filter by exact path
- `filter[beta]=true` / `filter[deprecated]=true` — include/exclude beta or deprecated
- `filter[definition.writeable]=true` — only writeable params
- `filter[definition.userSetting]=true` — only user-settable params
- `parameter-errors-as-data-attributes=true` — return per-parameter errors inline rather than failing the whole response (useful for batch reads)

> **Required for bulk reads:** Always include `parameter-errors-as-data-attributes=true` when reading `/wda/parameters` in bulk. Without it, any single unreadable parameter (e.g. `bacnet-datalinks-1-sc-mode` on FW31) returns HTTP 500 for the entire page. With the flag, failed parameters appear in `data[]` with `attributes.error` populated instead of a value. The `_paginate()` helper in `wda_client.py` injects this flag automatically for all `/wda/parameters` paths.
- `result-behavior=sync|async|auto` — for method invocation (POST /runs)
- `include=parameters` — for monitoring lists, return values inline

## Payload shapes (copy these)

### Set parameters (PATCH /wda/parameters)

```json
{
  "data": [
    {
      "id": "0-0-systemtime-local-now",
      "type": "parameters",
      "attributes": {"value": "2026-05-13T14:30:00"}
    }
  ]
}
```

### Invoke method (POST /wda/methods/{id}/runs)

```json
{
  "data": {
    "type": "runs",
    "attributes": {
      "inArgs": {
        "newpassword": {"value": "NewSecret123"}
      }
    }
  }
}
```

Note: each in-arg is wrapped as `{"value": ...}`, NOT flat. Each in-arg might also need a `stringValue` if the type is a 64-bit int (JavaScript precision issue).

### Method run response

```json
{
  "data": {
    "id": "1",
    "type": "runs",
    "attributes": {
      "executionStatus": "done",
      "outArgs": {"result": {"value": 42, "dataType": "uint32", "dataRank": "scalar"}},
      "timeout": 1234
    }
  }
}
```

`executionStatus`: `progress` | `done` | `error`. On error, also `title`, `detail`, optional `code` (WDA status code).

### Create monitoring list (POST /wda/monitoring-lists)

```json
{
  "data": {
    "type": "monitoring-lists",
    "attributes": {"timeout": 60},
    "relationships": {
      "parameters": {
        "data": [
          {"id": "0-0-identity-ordernumber", "type": "parameters"},
          {"id": "0-0-systemtime-local-now", "type": "parameters"}
        ]
      }
    }
  }
}
```

Add `?include=parameters` to get values inline in the response under `included[]`.

## WDA Status Codes (in error responses)

These appear as `errors[].code` and can be more specific than HTTP status:

| Code | Name | When |
|---|---|---|
| 2 | internal_error | Server problem |
| 4/5 | unknown_device | Device/collection not found |
| 17 | unknown_parameter_path | Parameter ID doesn't exist |
| 19 | not_a_method | ID points to a parameter, not a method |
| 20 | wrong_argument_count | Method call arg count mismatch |
| 21 | could_not_set_parameter | Set failed at PLC layer |
| 22 | missing_argument | Method missing required arg |
| 24 | wrong_value_type | Value doesn't match dataType |
| 26 | could_not_invoke_method | Method execution failed |
| 30 | wrong_value_pattern | String pattern violation |
| 31 | parameter_not_writeable | Read-only parameter |
| 36 | value_null | Null not allowed |
| 39 | invalid_value | Value invalid for some other reason |
| 41 | other_invalid_value_in_set | Bulk set rejected due to sibling |
| 44 | methods_do_not_have_value | Tried to GET value on a method ID |
| 46 | file_id_mismatch | Wrong file_id for the parameter |
| 51 | unknown_feature_name | Feature ID doesn't exist |

## Data types

| WDA type | JSON form | Notes |
|---|---|---|
| `string` | string | Apply output encoding when displaying |
| `boolean` | bool | |
| `uint8/16/32/64`, `int8/16/32/64` | integer | Use `stringValue` for 64-bit to avoid precision loss |
| `float32/64` | number | |
| `bytes` | base64 string | |
| `enum_member` | integer | Resolve via related enum-definition |
| `file_id` | string | Pair with File-API |
| `instance_ref` / `instance_identity_ref` | int / string | Limited direct use |
| `instantiations` | array of objects | Count items for class instance count; values opaque |

## Pagination

JSON:API style. Response has `links.next`, `links.prev`, `links.first`, `links.last`. Walk until `next` is absent:

```python
url = "/wda/parameters?page[limit]=255"
items = []
while url:
    r = client.get(url)
    body = r.json()
    page = body["data"]
    items.extend(page)
    if len(page) < page_limit:
        break  # defensive: shorter-than-full page means last page
    url = body.get("links", {}).get("next")
```

**Termination rules (verified FW31, WDA 1.5.2):**
- `links.next` is absent on the true last page — this is the primary signal.
- Add a secondary break when `len(data) < page[limit]` to guard against a corrupt or always-present `links.next`.
- The server hard-caps pages at **255 entries** regardless of the requested limit. Requesting `page[limit]=500` silently caps to 255.
- Parameters are returned in internal **registration order** — NOT alphabetical. Do not rely on sort order.

**URL encoding trap:** `page[limit]` and `page[offset]` MUST be sent via `--data-urlencode` (curl) or a proper query-param encoder — never embedded as literal bracket strings in a URL template. Literal embedding may be silently ignored by the WDA server, causing an infinite loop that repeatedly fetches page 0.

## Auth response headers

After successful auth via Basic, the server may include these for token use:

```
WAGO-WDX-Auth-Token: eyJhbGciOiAiSFM...
WAGO-WDX-Auth-Token-Type: Bearer
WAGO-WDX-Auth-Token-Expiration: 300
WAGO-WDX-Auth-Password-Expired: true  (only if applicable)
```

Token-based auth is faster on subsequent requests:

```
Authorization: Bearer eyJhbGciOiAiSFM...
```

The wago-plc-mcp server currently uses Basic auth only — that's fine for internal LANs but consider rotating credentials and using token auth at scale.

## Curl recipes for debugging

Replace `<plc_ip>` and `<user>:<pass>` with your actual values before running.

```bash
# 1. Check if PLC speaks WDX at all
curl -k -u <user>:<pass> https://<plc_ip>/wda

# 2. Get one parameter
curl -k -u <user>:<pass> https://<plc_ip>/wda/parameters/0-0-identity-ordernumber

# 3. Set a parameter
curl -k -u <user>:<pass> -X PATCH \
  -H 'Content-Type: application/vnd.api+json' \
  -d '{"data":{"type":"parameters","id":"0-0-systemtime-local-now","attributes":{"value":"2026-05-13T14:30:00"}}}' \
  https://<plc_ip>/wda/parameters/0-0-systemtime-local-now

# 4. Invoke a method (sync)
curl -k -u <user>:<pass> -X POST \
  -H 'Content-Type: application/vnd.api+json' \
  -d '{"data":{"type":"runs","attributes":{"inArgs":{}}}}' \
  "https://<plc_ip>/wda/methods/0-0-ntpclient-updatetime/runs?result-behavior=sync"

# 5. List writeable parameters only
curl -k -u <user>:<pass> \
  "https://<plc_ip>/wda/parameters?filter[definition.writeable]=true&page[limit]=10"

# 7. Full parameter dump — correct pagination (WDA hard-caps at 255/page)
# MUST use --data-urlencode; embedding page[offset] as a literal URL string causes
# the server to silently ignore the param and repeat page 0 forever.
IP=<plc_ip>
for offset in 0 255; do
  curl -sk -u <user>:<pass> -H "Accept: application/vnd.api+json" --max-time 90 \
    -G --data-urlencode "parameter-errors-as-data-attributes=true" \
       --data-urlencode "page[limit]=255" \
       --data-urlencode "page[offset]=${offset}" \
    "https://${IP}/wda/parameters"
done

# 6. Create monitoring list
curl -k -u <user>:<pass> -X POST \
  -H 'Content-Type: application/vnd.api+json' \
  -d '{"data":{"type":"monitoring-lists","attributes":{"timeout":60},"relationships":{"parameters":{"data":[{"id":"0-0-identity-ordernumber","type":"parameters"}]}}}}' \
  "https://<plc_ip>/wda/monitoring-lists?include=parameters"
```

## Limitations to be aware of

- `instantiations`, `instance_ref`, `instance_identity_ref` types — limited support, treat read-only
- No global validation metadata in the API (min/max ranges not exposed for numerics)
- Token refresh has a hard limit — fall back to Basic after long idle
- BETA-tagged resources can change without notice (use `filter[beta]=false` to exclude)
- Deprecated resources still work but will be removed — check `attributes.deprecated`

## When to come back to this file

- An MCP tool returns an obscure `error_code` → look it up in the WDA Status Codes table
- You need a feature the MCP server doesn't wrap (class instances, file uploads, deprecation flags)
- You're writing or debugging the MCP server itself
- A PLC's response shape looks unfamiliar and you want to compare to the spec
