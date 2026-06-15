"""Unit tests for enricher.py — L0, no network, no PLC."""
import types

import pytest

from enricher import enrich_method_definition, enrich_parameter, parse_watchlist_response


# ─────────────────────────── Fixtures ───────────────────────────


def _plc(
    param_to_enum: dict | None = None,
    enum_name: dict | None = None,
    enum_cases: dict | None = None,
    param_path: dict | None = None,
    param_writeable: set | None = None,
) -> types.SimpleNamespace:
    """Minimal PLC stub — only the attributes enrich_parameter reads."""
    return types.SimpleNamespace(
        param_to_enum=param_to_enum or {},
        enum_name=enum_name or {},
        enum_cases=enum_cases or {},
        param_path=param_path or {},
        param_writeable=param_writeable or set(),
    )


# ─────────────────────────── enrich_parameter ───────────────────────────


class TestEnrichParameterBoolean:
    def test_true_value_gives_activated_status(self) -> None:
        plc = _plc()
        result = enrich_parameter(plc, "p1", {"dataType": "boolean", "value": True})
        assert result["status"] == "Activated"

    def test_false_value_gives_deactivated_status(self) -> None:
        plc = _plc()
        result = enrich_parameter(plc, "p1", {"dataType": "boolean", "value": False})
        assert result["status"] == "Deactivated"

    def test_non_boolean_dtype_has_no_status_field(self) -> None:
        plc = _plc()
        result = enrich_parameter(plc, "p1", {"dataType": "uint8", "value": 42})
        assert "status" not in result


class TestEnrichParameterEnum:
    def _enum_plc(self) -> types.SimpleNamespace:
        return _plc(
            param_to_enum={"p1": "enum-42"},
            enum_name={"enum-42": "WebserverTransferProtocols"},
            enum_cases={
                "enum-42": [
                    {"value": 0, "stringValue": "HTTP"},
                    {"value": 1, "stringValue": "HTTPS"},
                    {"value": 2, "stringValue": "HTTP_HTTPS"},
                ]
            },
        )

    def test_enum_member_resolves_label(self) -> None:
        plc = self._enum_plc()
        result = enrich_parameter(plc, "p1", {"dataType": "enum_member", "value": 1})
        assert result["label"] == "HTTPS"

    def test_enum_member_resolves_enum_name(self) -> None:
        plc = self._enum_plc()
        result = enrich_parameter(plc, "p1", {"dataType": "enum_member", "value": 0})
        assert result["enum_name"] == "WebserverTransferProtocols"

    def test_unknown_enum_value_no_label_no_crash(self) -> None:
        plc = self._enum_plc()
        result = enrich_parameter(plc, "p1", {"dataType": "enum_member", "value": 99})
        assert "label" not in result
        assert result["enum_name"] == "WebserverTransferProtocols"

    def test_enum_member_no_mapping_in_param_to_enum(self) -> None:
        plc = _plc(
            enum_name={"enum-42": "SomeEnum"},
            enum_cases={"enum-42": [{"value": 0, "stringValue": "A"}]},
        )
        result = enrich_parameter(plc, "p1", {"dataType": "enum_member", "value": 0})
        assert "label" not in result
        assert "enum_name" not in result

    def test_first_enum_case_matched(self) -> None:
        plc = self._enum_plc()
        result = enrich_parameter(plc, "p1", {"dataType": "enum_member", "value": 0})
        assert result["label"] == "HTTP"

    def test_last_enum_case_matched(self) -> None:
        plc = self._enum_plc()
        result = enrich_parameter(plc, "p1", {"dataType": "enum_member", "value": 2})
        assert result["label"] == "HTTP_HTTPS"


class TestEnrichParameterWriteable:
    def test_writeable_true_when_pid_in_param_writeable(self) -> None:
        plc = _plc(param_writeable={"p1", "p2"})
        result = enrich_parameter(plc, "p1", {"dataType": "uint8", "value": 5})
        assert result["writeable"] is True

    def test_writeable_false_when_pid_not_in_param_writeable(self) -> None:
        plc = _plc(param_writeable={"p2"})
        result = enrich_parameter(plc, "p1", {"dataType": "uint8", "value": 5})
        assert result["writeable"] is False

    def test_writeable_always_present(self) -> None:
        plc = _plc()
        result = enrich_parameter(plc, "p1", {"dataType": "string", "value": "hi"})
        assert "writeable" in result


class TestEnrichParameterPath:
    def test_path_added_when_present_in_param_path(self) -> None:
        plc = _plc(param_path={"p1": "Device/Network/IPAddress"})
        result = enrich_parameter(plc, "p1", {"dataType": "string", "value": "10.0.0.1"})
        assert result["path"] == "Device/Network/IPAddress"

    def test_path_absent_when_not_in_param_path(self) -> None:
        plc = _plc(param_path={})
        result = enrich_parameter(plc, "p1", {"dataType": "string", "value": "hi"})
        assert "path" not in result

    def test_original_attrs_preserved(self) -> None:
        plc = _plc(param_path={"p1": "Some/Path"})
        attrs = {"dataType": "string", "value": "x", "extra": "keep"}
        result = enrich_parameter(plc, "p1", attrs)
        assert result["extra"] == "keep"
        assert result["dataType"] == "string"
        assert result["value"] == "x"

    def test_original_attrs_dict_not_mutated(self) -> None:
        plc = _plc(param_writeable={"p1"}, param_path={"p1": "Some/Path"})
        attrs = {"dataType": "boolean", "value": True}
        _ = enrich_parameter(plc, "p1", attrs)
        # Original dict must be untouched
        assert "status" not in attrs
        assert "path" not in attrs
        assert "writeable" not in attrs


# ─────────────────────────── parse_watchlist_response ───────────────────────────


class TestParseWatchlistResponse:
    def _body(self, included: list | None = None) -> dict:
        return {
            "data": {
                "id": "wl-1",
                "attributes": {"timeout": 60},
            },
            "included": included or [],
        }

    def test_empty_included_gives_empty_parameters(self) -> None:
        result = parse_watchlist_response(self._body())
        assert result["parameters"] == []

    def test_included_parameters_extracted(self) -> None:
        body = self._body(
            included=[
                {
                    "type": "parameters",
                    "id": "p1",
                    "attributes": {"value": 42, "dataType": "uint8", "error": None},
                }
            ]
        )
        result = parse_watchlist_response(body)
        assert len(result["parameters"]) == 1
        assert result["parameters"][0]["id"] == "p1"
        assert result["parameters"][0]["value"] == 42
        assert result["parameters"][0]["dataType"] == "uint8"

    def test_non_parameter_included_entries_ignored(self) -> None:
        body = self._body(
            included=[
                {"type": "monitoring-lists", "id": "ml-1", "attributes": {}},
                {"type": "parameters", "id": "p1", "attributes": {"value": 1, "dataType": "uint8"}},
            ]
        )
        result = parse_watchlist_response(body)
        assert len(result["parameters"]) == 1
        assert result["parameters"][0]["id"] == "p1"

    def test_error_attribute_preserved_when_present(self) -> None:
        body = self._body(
            included=[
                {
                    "type": "parameters",
                    "id": "p-err",
                    "attributes": {
                        "value": None,
                        "dataType": "uint8",
                        "error": {"code": 19, "message": "Access denied"},
                    },
                }
            ]
        )
        result = parse_watchlist_response(body)
        assert result["parameters"][0]["error"] == {"code": 19, "message": "Access denied"}

    def test_error_attribute_is_none_when_absent(self) -> None:
        body = self._body(
            included=[
                {"type": "parameters", "id": "p1", "attributes": {"value": 1, "dataType": "uint8"}}
            ]
        )
        result = parse_watchlist_response(body)
        assert result["parameters"][0]["error"] is None

    def test_top_level_id_and_timeout_extracted(self) -> None:
        result = parse_watchlist_response(self._body())
        assert result["id"] == "wl-1"
        assert result["timeout"] == 60

    def test_multiple_parameters_all_extracted(self) -> None:
        body = self._body(
            included=[
                {"type": "parameters", "id": f"p{i}", "attributes": {"value": i, "dataType": "uint8"}}
                for i in range(5)
            ]
        )
        result = parse_watchlist_response(body)
        assert len(result["parameters"]) == 5
        assert [p["id"] for p in result["parameters"]] == [f"p{i}" for i in range(5)]

    def test_missing_included_key_gives_empty_parameters(self) -> None:
        body = {"data": {"id": "wl-1", "attributes": {"timeout": 30}}}
        result = parse_watchlist_response(body)
        assert result["parameters"] == []


# ─────────────────────────── enrich_method_definition ───────────────────────────


class TestEnrichMethodDefinition:
    def _method(self) -> dict:
        return {
            "id": "0-0-ntpclient-updatetime",
            "type": "methods",
            "attributes": {"name": "Update NTP Time", "description": "Sync clock"},
        }

    def _in_args(self) -> list[dict]:
        return [
            {
                "id": "0-0-ntpclient-updatetime-server",
                "attributes": {
                    "name": "server",
                    "dataType": "string",
                    "dataRank": 0,
                    "description": "NTP server address",
                },
            }
        ]

    def _out_args(self) -> list[dict]:
        return [
            {
                "id": "0-0-ntpclient-updatetime-result",
                "attributes": {
                    "name": "result",
                    "dataType": "boolean",
                    "dataRank": 0,
                    "description": "Success indicator",
                },
            }
        ]

    def test_inArgs_inlined_into_attributes(self) -> None:
        result = enrich_method_definition(self._method(), self._in_args(), self._out_args())
        assert "inArgs" in result["attributes"]
        assert len(result["attributes"]["inArgs"]) == 1

    def test_outArgs_inlined_into_attributes(self) -> None:
        result = enrich_method_definition(self._method(), self._in_args(), self._out_args())
        assert "outArgs" in result["attributes"]
        assert len(result["attributes"]["outArgs"]) == 1

    def test_inArg_shape_shrunk_to_name_datatype_datarank(self) -> None:
        result = enrich_method_definition(self._method(), self._in_args(), self._out_args())
        arg = result["attributes"]["inArgs"][0]
        assert arg == {"name": "server", "dataType": "string", "dataRank": 0}
        assert "description" not in arg

    def test_outArg_shape_shrunk(self) -> None:
        result = enrich_method_definition(self._method(), self._in_args(), self._out_args())
        arg = result["attributes"]["outArgs"][0]
        assert arg == {"name": "result", "dataType": "boolean", "dataRank": 0}

    def test_empty_in_and_out_args(self) -> None:
        result = enrich_method_definition(self._method(), [], [])
        assert result["attributes"]["inArgs"] == []
        assert result["attributes"]["outArgs"] == []

    def test_existing_attributes_preserved(self) -> None:
        result = enrich_method_definition(self._method(), self._in_args(), self._out_args())
        assert result["attributes"]["name"] == "Update NTP Time"
        assert result["attributes"]["description"] == "Sync clock"

    def test_arg_without_attributes_falls_back_to_id_suffix(self) -> None:
        """When arg has no attributes block, name falls back to ID suffix."""
        in_args = [{"id": "method-argname"}]
        result = enrich_method_definition(self._method(), in_args, [])
        assert result["attributes"]["inArgs"][0]["name"] == "argname"

    def test_multiple_in_and_out_args_all_shrunk(self) -> None:
        in_args = [
            {"id": f"m-arg{i}", "attributes": {"name": f"in{i}", "dataType": "uint8", "dataRank": 0}}
            for i in range(3)
        ]
        out_args = [
            {"id": f"m-out{i}", "attributes": {"name": f"out{i}", "dataType": "string", "dataRank": 0}}
            for i in range(2)
        ]
        result = enrich_method_definition(self._method(), in_args, out_args)
        assert len(result["attributes"]["inArgs"]) == 3
        assert len(result["attributes"]["outArgs"]) == 2
        assert result["attributes"]["inArgs"][2]["name"] == "in2"
