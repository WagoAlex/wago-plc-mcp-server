"""Value enrichment helpers: resolve enums, attach human-readable labels."""
from typing import Any


def enrich_parameter(plc, pid: str, attrs: dict) -> dict:
    """Take raw WDA attributes and add agent-friendly fields.

    Adds:
      - status:       'Activated'/'Deactivated' for booleans
      - label:        enum's stringValue for enum_member types
      - enum_name:    the enum's name (e.g. 'WebserverTransferProtocols')
      - path:         human-readable path from the parameter definition
      - writeable:    boolean
    """
    out: dict[str, Any] = dict(attrs)
    dtype = attrs.get("dataType")
    value = attrs.get("value")

    if dtype == "boolean":
        out["status"] = "Activated" if value else "Deactivated"

    if dtype == "enum_member":
        eid = plc.param_to_enum.get(pid)
        if eid:
            out["enum_name"] = plc.enum_name.get(eid)
            for case in plc.enum_cases.get(eid, []):
                if case.get("value") == value:
                    out["label"] = case.get("stringValue")
                    break

    if pid in plc.param_path:
        out["path"] = plc.param_path[pid]
    out["writeable"] = pid in plc.param_writeable

    return out


def enrich_method_definition(method_data: dict, in_args: list[dict], out_args: list[dict]) -> dict:
    """Inline inArgs / outArgs into a method resource so an agent gets the full schema in one call."""

    def shrink(arg: dict) -> dict:
        a = arg.get("attributes", {})
        return {
            "name": a.get("name") or arg.get("id", "").rsplit("-", 1)[-1],
            "dataType": a.get("dataType"),
            "dataRank": a.get("dataRank"),
        }

    attrs = method_data.get("attributes", {})
    attrs["inArgs"] = [shrink(a) for a in in_args]
    attrs["outArgs"] = [shrink(a) for a in out_args]
    method_data["attributes"] = attrs
    return method_data


def parse_watchlist_response(body: dict) -> dict:
    """Extract {id, timeout, parameters: [{id, value, dataType}]} from a JSON:API monitoring-list response."""
    data = body.get("data", {})
    attrs = data.get("attributes", {})
    out: dict[str, Any] = {
        "id": data.get("id"),
        "timeout": attrs.get("timeout"),
        "parameters": [],
    }
    for inc in body.get("included", []):
        if inc.get("type") == "parameters":
            a = inc.get("attributes", {})
            out["parameters"].append({
                "id": inc.get("id"),
                "value": a.get("value"),
                "dataType": a.get("dataType"),
                "error": a.get("error"),  # only present if parameter-errors-as-data-attributes
            })
    return out
