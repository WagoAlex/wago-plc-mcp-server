"""TT4 — Data-type conformance tests (DT-01..DT-04).

Cases
──────
DT-01  uint64 param: value > 2^53 round-trips without precision loss.
       The WDA reference notes that 64-bit ints carry a ``stringValue`` alongside
       ``value`` to avoid JavaScript float64 truncation.  We assert:
         • get_parameter: ``stringValue`` preserved as-is in the enriched response.
         • set_parameters: the PATCH body contains the value unchanged (the raw
           Python int, which httpx serialises faithfully — no float conversion).

DT-02  enum_member: the client-level integer travels through without alteration.
       Enrichment label resolution lives in TT1/TT3; here we focus on the raw
       value round-trip (set sends int → read returns same int).

DT-03  boolean → ``status`` field; float32/64 → number preserved; bytes → base64
       string round-trip.

DT-04  invoke_method inArg wrapping: each arg becomes ``{"value": ...}`` — never
       flat.  Distinct from TT3's CT-06 (which uses a string arg).  We test:
         • a uint32 arg value
         • a large uint64 arg that needs ``stringValue`` treatment (assert the
           value > 2^53 is present as the raw int, not truncated)

No live network.  All HTTP is intercepted by respx.
"""
from __future__ import annotations

import json
import types

import httpx
import pytest
import respx

from enricher import enrich_parameter
from wda_client import WDAClient

from tests.contract.conftest import (
    CC100_IP,
    FAKE_USER,
    FAKE_PASS,
    _load,
    re_escape,
)

# ─────────────────────────── helpers ────────────────────────────────────────

UINT64_BIG = 9_999_999_999_999_999  # 9.999...e15 — well above 2^53 (≈9.007e15)


def _make_client(ip: str = CC100_IP) -> WDAClient:
    return WDAClient(ip, FAKE_USER, FAKE_PASS, timeout=5.0, ssl_verify=False)


def _si_response() -> httpx.Response:
    """Service-identity response that grants a Bearer token."""
    si = _load("cc100", "service_identity")
    return httpx.Response(si["status"], headers=si["headers"], json=si["body"])


def _minimal_plc_stub() -> types.SimpleNamespace:
    """Minimal PLCEntry-like namespace for enrich_parameter tests."""
    return types.SimpleNamespace(
        param_to_enum={
            "0-0-webserver-protocol": "enum-webserver-protocols",
        },
        enum_name={
            "enum-webserver-protocols": "WebserverTransferProtocols",
        },
        enum_cases={
            "enum-webserver-protocols": [
                {"value": 0, "stringValue": "HTTP"},
                {"value": 1, "stringValue": "HTTPS"},
                {"value": 2, "stringValue": "HTTP_HTTPS"},
            ]
        },
        param_path={"0-0-webserver-protocol": "Webserver/Protocol"},
        param_writeable={"0-0-webserver-protocol"},
    )


# ─────────────────────────── DT-01: uint64 / stringValue ────────────────────


class TestUint64StringValue:
    """DT-01 — 64-bit integer handled without JS precision loss."""

    async def test_get_parameter_preserves_string_value(self) -> None:
        """get_parameter passes ``stringValue`` through unchanged from the WDA response."""
        # Arrange — WDA returns value + stringValue for uint64
        param_body = {
            "data": {
                "id": "0-0-counter-ticks",
                "type": "parameters",
                "attributes": {
                    "value": UINT64_BIG,
                    "stringValue": str(UINT64_BIG),
                    "dataType": "uint64",
                    "dataRank": "scalar",
                },
            }
        }
        with respx.mock(assert_all_called=False) as router:
            router.get(f"https://{CC100_IP}/wda").mock(return_value=_si_response())
            router.get(
                url__regex=rf"^https://{re_escape(CC100_IP)}/wda/parameters/0-0-counter-ticks$"
            ).mock(return_value=httpx.Response(200, json=param_body))

            client = _make_client()
            try:
                attrs = await client.get_parameter("0-0-counter-ticks")
            finally:
                await client.close()

        # Assert — stringValue preserved as string, value as int
        assert attrs["stringValue"] == str(UINT64_BIG)
        assert attrs["value"] == UINT64_BIG
        # Critical: stringValue must NOT equal a float representation (precision loss)
        # float(UINT64_BIG) may equal the int due to rounding — use exact string check
        assert "." not in attrs["stringValue"], (
            "stringValue must be an exact integer string, not a float representation"
        )

    async def test_get_parameter_uint64_no_precision_loss(self) -> None:
        """Value > 2^53 survives get_parameter without integer truncation."""
        above_float_precision = 2**53 + 1  # 9007199254740993 — first int lost in float64
        param_body = {
            "data": {
                "id": "0-0-counter-ticks",
                "type": "parameters",
                "attributes": {
                    "value": above_float_precision,
                    "stringValue": str(above_float_precision),
                    "dataType": "uint64",
                    "dataRank": "scalar",
                },
            }
        }
        with respx.mock(assert_all_called=False) as router:
            router.get(f"https://{CC100_IP}/wda").mock(return_value=_si_response())
            router.get(
                url__regex=rf"^https://{re_escape(CC100_IP)}/wda/parameters/0-0-counter-ticks$"
            ).mock(return_value=httpx.Response(200, json=param_body))

            client = _make_client()
            try:
                attrs = await client.get_parameter("0-0-counter-ticks")
            finally:
                await client.close()

        # The exact value must be preserved — not truncated to 2^53
        assert attrs["value"] == above_float_precision, (
            f"Precision loss: expected {above_float_precision}, got {attrs['value']}"
        )
        assert attrs["stringValue"] == str(above_float_precision)

    async def test_set_parameters_uint64_value_not_truncated(self) -> None:
        """PATCH body carries the exact uint64 int — httpx must not lose precision."""
        captured: list[dict] = []

        def _capture(request: httpx.Request) -> httpx.Response:
            captured.append(json.loads(request.content))
            return httpx.Response(204)

        with respx.mock(assert_all_called=False) as router:
            router.get(f"https://{CC100_IP}/wda").mock(return_value=_si_response())
            router.patch(
                url__regex=rf"^https://{re_escape(CC100_IP)}/wda/parameters$"
            ).mock(side_effect=_capture)

            client = _make_client()
            try:
                await client.set_parameters([{"id": "0-0-counter-ticks", "value": UINT64_BIG}])
            finally:
                await client.close()

        assert len(captured) == 1, "PATCH /wda/parameters was never called"
        body = captured[0]
        sent_value = body["data"][0]["attributes"]["value"]
        # httpx serialises Python int faithfully; assert no truncation
        assert sent_value == UINT64_BIG, (
            f"uint64 precision loss in PATCH body: expected {UINT64_BIG}, got {sent_value}"
        )

    async def test_set_parameters_returns_ok_on_204(self) -> None:
        """set_parameters returns {'status': 'ok'} on 204 No Content."""
        with respx.mock(assert_all_called=False) as router:
            router.get(f"https://{CC100_IP}/wda").mock(return_value=_si_response())
            router.patch(
                url__regex=rf"^https://{re_escape(CC100_IP)}/wda/parameters$"
            ).mock(return_value=httpx.Response(204))

            client = _make_client()
            try:
                result = await client.set_parameters(
                    [{"id": "0-0-counter-ticks", "value": UINT64_BIG}]
                )
            finally:
                await client.close()

        assert result == {"status": "ok"}


# ─────────────────────────── DT-02: enum_member int round-trip ──────────────


class TestEnumMemberIntRoundTrip:
    """DT-02 — enum_member: integer value passes through the client unchanged."""

    async def test_get_parameter_enum_value_is_integer(self) -> None:
        """Raw client get_parameter returns the enum integer, not a string or label."""
        param_body = {
            "data": {
                "id": "0-0-webserver-protocol",
                "type": "parameters",
                "attributes": {
                    "value": 1,
                    "dataType": "enum_member",
                    "dataRank": "scalar",
                },
            }
        }
        with respx.mock(assert_all_called=False) as router:
            router.get(f"https://{CC100_IP}/wda").mock(return_value=_si_response())
            router.get(
                url__regex=rf"^https://{re_escape(CC100_IP)}/wda/parameters/0-0-webserver-protocol$"
            ).mock(return_value=httpx.Response(200, json=param_body))

            client = _make_client()
            try:
                attrs = await client.get_parameter("0-0-webserver-protocol")
            finally:
                await client.close()

        # Client layer: raw integer, no label
        assert attrs["value"] == 1
        assert isinstance(attrs["value"], int)
        assert attrs["dataType"] == "enum_member"

    def test_enrich_parameter_adds_label_to_enum_member(self) -> None:
        """enrich_parameter converts int → label on top of the raw client result."""
        plc = _minimal_plc_stub()
        attrs = {"dataType": "enum_member", "value": 1, "dataRank": "scalar"}

        result = enrich_parameter(plc, "0-0-webserver-protocol", attrs)

        # Label layer on top of the integer
        assert result["value"] == 1
        assert result["label"] == "HTTPS"
        assert result["enum_name"] == "WebserverTransferProtocols"

    async def test_set_parameters_enum_sends_integer(self) -> None:
        """PATCH body for enum_member carries an integer, not a string label."""
        captured: list[dict] = []

        def _capture(request: httpx.Request) -> httpx.Response:
            captured.append(json.loads(request.content))
            return httpx.Response(204)

        with respx.mock(assert_all_called=False) as router:
            router.get(f"https://{CC100_IP}/wda").mock(return_value=_si_response())
            router.patch(
                url__regex=rf"^https://{re_escape(CC100_IP)}/wda/parameters$"
            ).mock(side_effect=_capture)

            client = _make_client()
            try:
                await client.set_parameters(
                    [{"id": "0-0-webserver-protocol", "value": 2}]
                )
            finally:
                await client.close()

        body = captured[0]
        sent_value = body["data"][0]["attributes"]["value"]
        assert sent_value == 2
        assert isinstance(sent_value, int), "enum_member set must send integer, not string"


# ─────────────────────────── DT-03: boolean / float / bytes ─────────────────


class TestOtherDataTypes:
    """DT-03 — boolean status field; float preserved; bytes as base64 string."""

    def test_boolean_true_adds_activated_status(self) -> None:
        """boolean value=True → status='Activated' via enrich_parameter."""
        plc = types.SimpleNamespace(
            param_to_enum={}, enum_name={}, enum_cases={},
            param_path={"0-0-webserver-enabled": "Webserver/Enabled"},
            param_writeable={"0-0-webserver-enabled"},
        )
        attrs = {"dataType": "boolean", "value": True, "dataRank": "scalar"}
        result = enrich_parameter(plc, "0-0-webserver-enabled", attrs)
        assert result["status"] == "Activated"
        assert result["value"] is True

    def test_boolean_false_adds_deactivated_status(self) -> None:
        """boolean value=False → status='Deactivated' via enrich_parameter."""
        plc = types.SimpleNamespace(
            param_to_enum={}, enum_name={}, enum_cases={},
            param_path={}, param_writeable=set(),
        )
        attrs = {"dataType": "boolean", "value": False, "dataRank": "scalar"}
        result = enrich_parameter(plc, "0-0-some-flag", attrs)
        assert result["status"] == "Deactivated"
        assert result["value"] is False

    async def test_get_parameter_float32_preserved(self) -> None:
        """float32 value round-trips as a Python float, not an int or string."""
        float_value = 3.14159
        param_body = {
            "data": {
                "id": "0-0-sensor-temperature",
                "type": "parameters",
                "attributes": {
                    "value": float_value,
                    "dataType": "float32",
                    "dataRank": "scalar",
                },
            }
        }
        with respx.mock(assert_all_called=False) as router:
            router.get(f"https://{CC100_IP}/wda").mock(return_value=_si_response())
            router.get(
                url__regex=rf"^https://{re_escape(CC100_IP)}/wda/parameters/0-0-sensor-temperature$"
            ).mock(return_value=httpx.Response(200, json=param_body))

            client = _make_client()
            try:
                attrs = await client.get_parameter("0-0-sensor-temperature")
            finally:
                await client.close()

        assert attrs["dataType"] == "float32"
        # json.loads parses JSON numbers as float; assert it's not coerced to int
        assert isinstance(attrs["value"], float)
        assert abs(attrs["value"] - float_value) < 1e-4

    async def test_get_parameter_float64_preserved(self) -> None:
        """float64 value round-trips without truncation."""
        float_value = 1.23456789012345
        param_body = {
            "data": {
                "id": "0-0-sensor-precise",
                "type": "parameters",
                "attributes": {
                    "value": float_value,
                    "dataType": "float64",
                    "dataRank": "scalar",
                },
            }
        }
        with respx.mock(assert_all_called=False) as router:
            router.get(f"https://{CC100_IP}/wda").mock(return_value=_si_response())
            router.get(
                url__regex=rf"^https://{re_escape(CC100_IP)}/wda/parameters/0-0-sensor-precise$"
            ).mock(return_value=httpx.Response(200, json=param_body))

            client = _make_client()
            try:
                attrs = await client.get_parameter("0-0-sensor-precise")
            finally:
                await client.close()

        assert attrs["dataType"] == "float64"
        assert isinstance(attrs["value"], float)
        assert abs(attrs["value"] - float_value) < 1e-10

    async def test_get_parameter_bytes_base64_string(self) -> None:
        """bytes type: WDA returns a base64 string; client passes it through unchanged."""
        b64_value = "SGVsbG8gV0FHTWCP"  # base64 of some bytes
        param_body = {
            "data": {
                "id": "0-0-tls-cert-fingerprint",
                "type": "parameters",
                "attributes": {
                    "value": b64_value,
                    "dataType": "bytes",
                    "dataRank": "scalar",
                },
            }
        }
        with respx.mock(assert_all_called=False) as router:
            router.get(f"https://{CC100_IP}/wda").mock(return_value=_si_response())
            router.get(
                url__regex=rf"^https://{re_escape(CC100_IP)}/wda/parameters/0-0-tls-cert-fingerprint$"
            ).mock(return_value=httpx.Response(200, json=param_body))

            client = _make_client()
            try:
                attrs = await client.get_parameter("0-0-tls-cert-fingerprint")
            finally:
                await client.close()

        assert attrs["dataType"] == "bytes"
        assert attrs["value"] == b64_value
        assert isinstance(attrs["value"], str), (
            "bytes type must arrive as a base64 string, not decoded bytes"
        )

    async def test_set_parameters_bytes_roundtrip(self) -> None:
        """bytes type set: base64 string goes in, comes back unchanged in PATCH body."""
        b64_value = "SGVsbG8gV0FHTw=="
        captured: list[dict] = []

        def _capture(request: httpx.Request) -> httpx.Response:
            captured.append(json.loads(request.content))
            return httpx.Response(204)

        with respx.mock(assert_all_called=False) as router:
            router.get(f"https://{CC100_IP}/wda").mock(return_value=_si_response())
            router.patch(
                url__regex=rf"^https://{re_escape(CC100_IP)}/wda/parameters$"
            ).mock(side_effect=_capture)

            client = _make_client()
            try:
                await client.set_parameters(
                    [{"id": "0-0-tls-cert-fingerprint", "value": b64_value}]
                )
            finally:
                await client.close()

        sent_value = captured[0]["data"][0]["attributes"]["value"]
        assert sent_value == b64_value
        assert isinstance(sent_value, str)


# ─────────────────────────── DT-04: invoke_method inArg wrapping ────────────


class TestInvokeMethodInArgWrapping:
    """DT-04 — inArgs always wrapped as {name: {'value': ...}} — never flat.

    Distinct from TT3/CT-06 which used a string arg. This suite adds:
      • uint32 numeric arg
      • uint64 arg > 2^53 (stringValue candidate — the SENDING side)
    """

    async def _capture_post_body(
        self, method_id: str, arguments: dict
    ) -> dict:
        """Helper: invoke_method and return the captured POST JSON body."""
        captured: list[dict] = []
        run_response = {
            "data": {
                "id": "1",
                "type": "runs",
                "attributes": {
                    "executionStatus": "done",
                    "outArgs": {},
                },
            }
        }

        def _capture(request: httpx.Request) -> httpx.Response:
            captured.append(json.loads(request.content))
            return httpx.Response(200, json=run_response)

        with respx.mock(assert_all_called=False) as router:
            router.get(f"https://{CC100_IP}/wda").mock(return_value=_si_response())
            router.post(
                url__regex=rf"^https://{re_escape(CC100_IP)}/wda/methods/.+/runs.*$"
            ).mock(side_effect=_capture)

            client = _make_client()
            try:
                await client.invoke_method(method_id, arguments)
            finally:
                await client.close()

        assert len(captured) == 1, "POST to /runs was never captured"
        return captured[0]

    async def test_uint32_inarg_wrapped_not_flat(self) -> None:
        """uint32 argument: body['data']['attributes']['inArgs']['count'] == {'value': 42}."""
        body = await self._capture_post_body(
            "0-0-logger-rotate", {"count": 42}
        )
        in_args = body["data"]["attributes"]["inArgs"]
        assert "count" in in_args, "inArg 'count' missing from request body"
        assert isinstance(in_args["count"], dict), (
            f"inArg must be wrapped dict, got {type(in_args['count'])}: {in_args['count']!r}"
        )
        assert "value" in in_args["count"], "inArg must have a 'value' key"
        assert in_args["count"]["value"] == 42
        # Confirm it is NOT flat (i.e. the value is not directly at the arg name)
        assert not isinstance(in_args.get("count"), int), (
            "inArg must not be a flat integer — must be {'value': 42}"
        )

    async def test_uint64_inarg_value_preserved_above_float_precision(self) -> None:
        """uint64 arg > 2^53 arrives in the POST body without truncation.

        Python's httpx serialises int faithfully; this test guards against
        any future intermediate that might coerce to float.
        """
        large_int = 2**53 + 7  # 9007199254740999 — above float64 precision boundary
        body = await self._capture_post_body(
            "0-0-diagnostics-setcounter", {"tick": large_int}
        )
        in_args = body["data"]["attributes"]["inArgs"]
        assert "tick" in in_args
        assert isinstance(in_args["tick"], dict), "uint64 inArg must be wrapped dict"
        assert "value" in in_args["tick"]
        assert in_args["tick"]["value"] == large_int, (
            f"Precision loss: expected {large_int}, got {in_args['tick']['value']}"
        )

    async def test_string_inarg_still_wrapped(self) -> None:
        """Regression: string args also use {'value': ...}, not flat."""
        body = await self._capture_post_body(
            "0-0-usermanagement-changepassword", {"newpassword": "S3cr3t!"}
        )
        in_args = body["data"]["attributes"]["inArgs"]
        assert isinstance(in_args["newpassword"], dict)
        assert in_args["newpassword"]["value"] == "S3cr3t!"

    async def test_no_inargs_produces_empty_dict(self) -> None:
        """Calling with no arguments → inArgs is an empty dict {}."""
        body = await self._capture_post_body("0-0-ntpclient-updatetime", {})
        in_args = body["data"]["attributes"]["inArgs"]
        assert in_args == {}

    async def test_multiple_inargs_all_wrapped(self) -> None:
        """Multiple args: each individually wrapped — none is flat."""
        body = await self._capture_post_body(
            "0-0-some-method",
            {"alpha": 1, "beta": "hello", "gamma": True},
        )
        in_args = body["data"]["attributes"]["inArgs"]
        for arg_name, raw_value in [("alpha", 1), ("beta", "hello"), ("gamma", True)]:
            assert arg_name in in_args, f"inArg '{arg_name}' missing"
            assert isinstance(in_args[arg_name], dict), (
                f"'{arg_name}' must be wrapped, got {type(in_args[arg_name])}"
            )
            assert in_args[arg_name]["value"] == raw_value
