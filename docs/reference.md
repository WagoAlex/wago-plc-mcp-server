# Reference

## Tool reference

### Discovery

| Tool | Description |
|------|-------------|
| `list_plcs` | Lists the IPs of all registered PLCs |
| `describe_plc(plc_ip)` | Returns capability counts, feature names, `device_class`, `expected_parameter_count`, and `parameter_count_ok` |
| `get_plc_audit_log(plc_ip, action, limit)` | Reads recent audit log entries, newest first (max 500). Filters by PLC and action. |
| `get_device(plc_ip, device_id)` | Returns a device and its features |
| `get_feature(plc_ip, feature_id)` | Returns a feature with nested features and parameter and method definitions |
| `get_enum_definition(plc_ip, enum_id)` | Returns all cases of an enum (value → stringValue) |
| `get_parameter_definition(plc_ip, parameter_id)` | Returns writeable, userSetting, dataType, and enum link without reading the value |

### Parameters

| Tool | Description |
|------|-------------|
| `find_parameters(plc_ip, query, writeable_only, user_settings_only, limit)` | Searches by keyword (default 20 results, max 255) |
| `get_parameter(plc_ip, parameter_id)` | Reads one value with enum labels |
| `get_parameters_bulk(requests)` | Reads one parameter from many PLCs in parallel |
| `set_parameters(plc_ip, parameters)` | Writes one or more parameters (bulk PATCH) |
| `set_parameter(plc_ip, parameter_id, value)` | Writes one parameter |
| `get_parameter_referenced_instances(plc_ip, parameter_id)` | Returns the instances that an `instance_identity_ref` parameter refers to |
| `list_parameter_instances(plc_ip, parameter_id)` | Returns the instance numbers of a class-typed parameter |
| `get_parameter_instance(plc_ip, parameter_id, instance_no)` | Returns one instance with its device, parameters, and methods |

### Methods

| Tool | Description |
|------|-------------|
| `find_methods(plc_ip, query, limit)` | Searches by keyword |
| `get_method(plc_ip, method_id)` | Returns the inArgs and outArgs schema |
| `invoke_method(plc_ip, method_id, arguments, wait)` | Runs a method synchronously or asynchronously |
| `get_method_run(plc_ip, method_id, run_id)` | Returns the status of an asynchronous run |
| `list_method_runs(plc_ip, method_id)` | Lists the runs that the PLC still keeps |
| `delete_method_run(plc_ip, method_id, run_id)` | Deletes a run result on the PLC |

### Watchlists

| Tool | Description |
|------|-------------|
| `list_watchlists(plc_ip)` | Lists the active watchlist IDs on the PLC |
| `create_watchlist(plc_ip, parameter_ids, timeout_seconds)` | Makes a watchlist on the PLC |
| `read_watchlist(plc_ip, watchlist_id)` | Returns the values of all parameters in the list in one HTTP request |
| `delete_watchlist(plc_ip, watchlist_id)` | Deletes the watchlist immediately |

**Why watchlists:** Each `get_parameter` call opens a new HTTPS connection.
For 10 parameters on 15 PLCs every 30 seconds, that is 150 HTTPS requests in each cycle.
One `read_watchlist` call returns all values in one request.

### Files (file_id parameters)

| Tool | Description |
|------|-------------|
| `create_file(plc_ip, context_parameter_id)` | Gets a file_id for an upload |
| `upload_file(plc_ip, file_id, content_base64, content_type)` | Uploads the full file content (base64) |
| `download_file(plc_ip, file_id)` | Downloads the file content as base64 |
| `get_file_metadata(plc_ip, file_id)` | Returns size and type without the file content |

> [!NOTE]
> The class-instance and file tools follow the WDA specification, but we did not test them on real hardware.
> No device in our test fleet has an `instantiations` or `file_id` parameter. See `docs/functional-test-status.md`.

### Example workflows

**Read the firmware version from many PLCs in one call:**

```
get_parameters_bulk([
  {"plc_ip": "192.168.1.10", "parameter_id": "0-0-version-firmwareversion"},
  {"plc_ip": "192.168.1.11", "parameter_id": "0-0-version-firmwareversion"}
])
```

**Start an NTP time sync on one PLC:**

```
find_methods("192.168.1.10", "ntp")
→ ["0-0-ntpclient-updatetime"]

invoke_method("192.168.1.10", "0-0-ntpclient-updatetime", wait=True)
→ {"status": "done", "run_id": "1", "out_args": {}}
```

**Monitor health with a watchlist:**

```
create_watchlist("192.168.1.10", [
  "0-0-ledstates-1-diagnosticinformation",
  "0-0-ledstates-4-diagnosticinformation",
  "0-0-ntpclient-isrunning",
  "0-0-docker-isrunning",
  "0-0-cloudconnections-1-status-connected"
], timeout_seconds=300)

read_watchlist("192.168.1.10", "1")   # call every 30 s
delete_watchlist("192.168.1.10", "1") # explicit cleanup when done
```

## Configuration reference

The Claude Desktop extension shows each of these settings in its install form, except `HOST`, `PORT`, `TRANSPORT`, `MCP_API_KEY`, and `MCP_TLS_*`.
These settings apply only to the HTTP server. The extension always uses stdio.

| Variable | Default | Description |
|----------|---------|-------------|
| `WAGO_PLC_HOSTS` | - | PLC IPs, separated by commas |
| `WAGO_PLC_HOSTS_FILE` | - | Path to a file with one IP per line |
| `DEFAULT_PLC_USERNAME` | `admin` | Shared username |
| `DEFAULT_PLC_PASSWORD` | `wago` | Shared password. Use a Docker Secret instead. |
| `PLC_PASSWORDS` | - | Per-PLC passwords as `ip=pwd,ip=pwd` |
| `PLC_PASSWORDS_FILE` | - | Path to a file with one `ip=pwd` per line (`#` comments) |
| `PLC_PASSWORDS_<ip_underscores>` | - | Password for one PLC |
| `MCP_API_KEY` | - | Bearer token for `/mcp`. The server makes one if this is not set. |
| `GITOPS_MODE` | `0` | `1` returns YAML fragments instead of writes |
| `WAGO_GITOPS_REPO` | `wago-plc-config` | Config repository name in the `next_step` of the returned YAML. Set it for a fork or a renamed repository. |
| `WAGO_READONLY_HOSTS` | - | PLC IPs, separated by commas, that refuse `set_parameters`, `invoke_method`, and file uploads in all modes |
| `WAGO_ALLOW_WRITES` | - (writes allowed) | Fleet-wide switch. `true` allows writes. All other values (`false`, empty) make **all** PLCs read-only. |
| `WAGO_ALLOW_METHODS` | - | Exact method IDs, separated by commas, that live mode allows from the dangerous-method list |
| `WAGO_TLS_CA` | - | WDA TLS: `false` (off), `true` (system CA), or a path |
| `MCP_TLS_CERT` | - | Path to the TLS certificate for the MCP endpoint |
| `MCP_TLS_KEY` | - | Path to the TLS private key for the MCP endpoint |
| `MCP_TLS_KEY_PASSWORD` | - | Password for an encrypted TLS private key |
| `SECURITY_PROFILE` | - | `hardened` stops the server at startup if `WAGO_TLS_CA` is not set. With the HTTP transport, `MCP_TLS_CERT` and `MCP_TLS_KEY` are also necessary. With stdio, they are not, because stdio has no network connection |
| `AUDIT_LOG_FILE` | `/app/data/audit.log` | Audit log path in the container |
| `AUDIT_SYSLOG` | - | Sends audit records to syslog, for example `udp://10.0.0.5:514` or `tcp://...` |
| `SYSLOG_HOST` | - | Syslog or SIEM host that receives the audit entries. When set, the server keeps 2 local audit files instead of 5 |
| `SYSLOG_PORT` | `514` | Syslog port |
| `SYSLOG_TCP` | `false` | `true` = TCP (reliable), `false` = UDP |
| `TRANSPORT` | `streamable-http` | `streamable-http`, `sse`, or `stdio` |
| `HOST` | `0.0.0.0` | Bind address |
| `PORT` | `6042` | Listen port |
| `WAGO_TIMEOUT_SECONDS` | `45` | HTTP timeout for each PLC. CC100 needs 45 or more. |
| `WAGO_PAGE_LIMIT` | `500` | WDA page size |
| `WAGO_MAX_CONCURRENT_REGISTRATIONS` | `5` | Maximum PLC registrations in parallel |
| `WAGO_MAX_CONCURRENT_READS` | `10` | Maximum PLC requests in parallel in `get_parameters_bulk` |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, or `ERROR` |
| `LOG_FILE` | `/app/mcp_server.log` | Debug log path in the container |

## Raw WDA access with curl

Use curl for bulk exports, debugging, or test cassettes. This bypasses the MCP layer.

- WDA returns a maximum of 255 entries on each page. Most device classes need two pages.
- Always include `parameter-errors-as-data-attributes=true`.
- Send `page[limit]` and `page[offset]` with `--data-urlencode`. If you put the brackets directly in the URL, WDA ignores them and the loop never ends.

```bash
IP=192.168.1.10
OUT=wda-parameters-${IP}.json

{
  curl -sk -u "admin:wago" -H "Accept: application/vnd.api+json" --max-time 90 \
    -G --data-urlencode "parameter-errors-as-data-attributes=true" \
       --data-urlencode "page[limit]=255" \
       --data-urlencode "page[offset]=0" \
    "https://${IP}/wda/parameters"
  curl -sk -u "admin:wago" -H "Accept: application/vnd.api+json" --max-time 90 \
    -G --data-urlencode "parameter-errors-as-data-attributes=true" \
       --data-urlencode "page[limit]=255" \
       --data-urlencode "page[offset]=255" \
    "https://${IP}/wda/parameters"
} | jq -s '{data: (map(.data) | add)}' > "$OUT"

echo "Saved $(jq '.data | length' "$OUT") parameters to $OUT"
```
