"""TT3 — L1 contract / cassette tests.

Cases
──────
CT-02  _cache_resources populates all ID sets + rich metadata correctly.
CT-03  CC100 empty features list → register succeeds, features == set().
CT-04  Edge 2-page parameters → _paginate merges both pages.
CT-05  enrich_parameter on a real enum_member cassette blob → correct label.
CT-06  invoke_method run responses: done / progress / error → right data dict.
CT-07  Stale-cassette guard: firmware mismatch → clear "re-record" message.
       + scrub() unit test.

No live network.  All HTTP is intercepted by respx (see conftest.py).
"""
from __future__ import annotations

import json
import types
from pathlib import Path

import pytest

from enricher import enrich_parameter
from plc_manager import PLCManager
from wda_client import WDAClient

from tests.contract.conftest import (
    CC100_IP,
    EDGE_IP,
    PFC200_IP,
    FAKE_USER,
    FAKE_PASS,
    _load,
)

# ─────────────────────────── helpers ────────────────────────────────────────


def _make_client(ip: str) -> WDAClient:
    """Instantiate a WDAClient pointing at a fake IP with SSL disabled."""
    return WDAClient(ip, FAKE_USER, FAKE_PASS, timeout=5.0, ssl_verify=False)


async def _register(ip: str) -> object:
    """Run PLCManager.register() with fake creds; returns PLCEntry or None."""
    mgr = PLCManager(timeout_seconds=5.0, ssl_verify=False)
    return await mgr.register(ip, FAKE_USER, FAKE_PASS)


# ─────────────────────────── CT-02: _cache_resources ────────────────────────


class TestCacheResources:
    """CT-02 — _cache_resources populates all expected sets and dicts."""

    async def test_cc100_parameters_set_populated(self, cc100_router) -> None:
        entry = await _register(CC100_IP)
        assert entry is not None
        assert "0-0-identity-ordernumber" in entry.parameters
        assert "0-0-network-ipaddress" in entry.parameters
        assert "0-0-webserver-protocol" in entry.parameters

    async def test_cc100_methods_set_populated(self, cc100_router) -> None:
        entry = await _register(CC100_IP)
        assert entry is not None
        assert "0-0-ntpclient-updatetime" in entry.methods
        assert "0-0-usermanagement-changepassword" in entry.methods

    async def test_cc100_devices_set_populated(self, cc100_router) -> None:
        entry = await _register(CC100_IP)
        assert entry is not None
        assert "0-0" in entry.devices

    async def test_cc100_param_path_populated(self, cc100_router) -> None:
        entry = await _register(CC100_IP)
        assert entry is not None
        assert entry.param_path["0-0-identity-ordernumber"] == "Identity/OrderNumber"
        assert entry.param_path["0-0-network-ipaddress"] == "Network/IPAddress"
        assert entry.param_path["0-0-webserver-protocol"] == "Webserver/Protocol"

    async def test_cc100_param_writeable_populated(self, cc100_router) -> None:
        entry = await _register(CC100_IP)
        assert entry is not None
        # writeable params
        assert "0-0-identity-hostname" in entry.param_writeable
        assert "0-0-network-ipaddress" in entry.param_writeable
        assert "0-0-webserver-protocol" in entry.param_writeable
        # read-only params must NOT appear
        assert "0-0-identity-ordernumber" not in entry.param_writeable
        assert "0-0-identity-firmware" not in entry.param_writeable

    async def test_cc100_param_user_setting_populated(self, cc100_router) -> None:
        entry = await _register(CC100_IP)
        assert entry is not None
        assert "0-0-identity-hostname" in entry.param_user_setting
        assert "0-0-network-ipaddress" in entry.param_user_setting
        # non-userSetting params must NOT appear
        assert "0-0-systemtime-local-now" not in entry.param_user_setting

    async def test_cc100_param_to_enum_populated(self, cc100_router) -> None:
        entry = await _register(CC100_IP)
        assert entry is not None
        assert entry.param_to_enum["0-0-webserver-protocol"] == "enum-webserver-protocols"
        # params without enum relation must not appear
        assert "0-0-identity-ordernumber" not in entry.param_to_enum

    async def test_cc100_enum_cases_populated(self, cc100_router) -> None:
        entry = await _register(CC100_IP)
        assert entry is not None
        cases = entry.enum_cases["enum-webserver-protocols"]
        assert len(cases) == 3
        values = [c["value"] for c in cases]
        labels = [c["stringValue"] for c in cases]
        assert 0 in values
        assert 1 in values
        assert "HTTP" in labels
        assert "HTTPS" in labels
        assert "HTTP_HTTPS" in labels

    async def test_cc100_enum_name_populated(self, cc100_router) -> None:
        entry = await _register(CC100_IP)
        assert entry is not None
        assert entry.enum_name["enum-webserver-protocols"] == "WebserverTransferProtocols"

    async def test_pfc200_parameters_and_enum_populated(self, pfc200_router) -> None:
        entry = await _register(PFC200_IP)
        assert entry is not None
        assert "0-0-fieldbus-protocol" in entry.parameters
        assert entry.param_to_enum["0-0-fieldbus-protocol"] == "enum-fieldbus-protocols"
        cases = entry.enum_cases["enum-fieldbus-protocols"]
        assert any(c["stringValue"] == "PROFIBUS" for c in cases)


# ─────────────────────────── CT-03: empty features ──────────────────────────


class TestEmptyFeatures:
    """CT-03 — CC100 cassette has empty features list; register must still succeed."""

    async def test_register_succeeds_with_empty_features(self, cc100_router) -> None:
        entry = await _register(CC100_IP)
        assert entry is not None

    async def test_features_set_is_empty(self, cc100_router) -> None:
        entry = await _register(CC100_IP)
        assert entry is not None
        assert entry.features == set()

    async def test_parameters_and_methods_still_populated(self, cc100_router) -> None:
        """Essential resources (params + methods) must be present despite empty features."""
        entry = await _register(CC100_IP)
        assert entry is not None
        assert len(entry.parameters) > 0
        assert len(entry.methods) > 0

    async def test_edge_has_non_empty_features(self, edge_router) -> None:
        """Control: Edge cassette has features; confirm the contrast."""
        entry = await _register(EDGE_IP)
        assert entry is not None
        assert len(entry.features) > 0
        assert "feature-cloud-connectivity" in entry.features
        assert "feature-container-runtime" in entry.features


# ─────────────────────────── CT-04: pagination ──────────────────────────────


class TestPagination:
    """CT-04 — Edge 2-page parameters cassette: _paginate walks both pages."""

    async def test_all_parameters_from_both_pages_merged(self, edge_router) -> None:
        # Page 1 has 5 items; page 2 has 3 items → total 8.
        p1 = _load("edge", "parameters_page1")
        p2 = _load("edge", "parameters_page2")
        expected_count = len(p1["body"]["data"]) + len(p2["body"]["data"])

        client = _make_client(EDGE_IP)
        try:
            items = await client.list_parameters()
        finally:
            await client.close()

        assert len(items) == expected_count

    async def test_page1_ids_present_in_merged_result(self, edge_router) -> None:
        p1 = _load("edge", "parameters_page1")
        page1_ids = {item["id"] for item in p1["body"]["data"]}

        client = _make_client(EDGE_IP)
        try:
            items = await client.list_parameters()
        finally:
            await client.close()

        merged_ids = {item["id"] for item in items}
        assert page1_ids.issubset(merged_ids)

    async def test_page2_ids_present_in_merged_result(self, edge_router) -> None:
        p2 = _load("edge", "parameters_page2")
        page2_ids = {item["id"] for item in p2["body"]["data"]}

        client = _make_client(EDGE_IP)
        try:
            items = await client.list_parameters()
        finally:
            await client.close()

        merged_ids = {item["id"] for item in items}
        assert page2_ids.issubset(merged_ids)

    async def test_page1_links_next_present_in_cassette(self) -> None:
        """Sanity: the cassette itself has links.next so pagination fires."""
        p1 = _load("edge", "parameters_page1")
        assert p1["body"]["links"].get("next") is not None

    async def test_page2_links_next_absent_in_cassette(self) -> None:
        """Sanity: the second cassette has no links.next so pagination stops."""
        p2 = _load("edge", "parameters_page2")
        assert not p2["body"]["links"].get("next")

    async def test_cc100_single_page_not_affected(self, cc100_router) -> None:
        """Control: CC100 has one page; count matches cassette exactly."""
        p1 = _load("cc100", "parameters_page1")
        expected = len(p1["body"]["data"])

        client = _make_client(CC100_IP)
        try:
            items = await client.list_parameters()
        finally:
            await client.close()

        assert len(items) == expected


# ─────────────────────────── CT-05: enrich_parameter with cassette enum ─────


class TestEnrichParameterCassette:
    """CT-05 — enrich_parameter on real cassette enum_member attributes."""

    def _plc_from_cassettes(self, cls: str) -> types.SimpleNamespace:
        """Build a minimal PLC stub from the class's cassette files."""
        pd_cas = _load(cls, "parameter_definitions")
        enum_cas = _load(cls, "enum_definitions")

        param_to_enum: dict[str, str] = {}
        param_path: dict[str, str] = {}
        param_writeable: set[str] = set()
        param_user_setting: set[str] = set()

        for pdef in pd_cas["body"]["data"]:
            pid = pdef["id"]
            attrs = pdef.get("attributes", {})
            if attrs.get("path"):
                param_path[pid] = attrs["path"]
            if attrs.get("writeable"):
                param_writeable.add(pid)
            if attrs.get("userSetting"):
                param_user_setting.add(pid)
            rel = pdef.get("relationships", {}).get("enum", {}).get("data")
            if rel and "id" in rel:
                param_to_enum[pid] = rel["id"]

        enum_name: dict[str, str] = {}
        enum_cases: dict[str, list] = {}
        for edef in enum_cas["body"]["data"]:
            eid = edef["id"]
            e_attrs = edef.get("attributes", {})
            enum_name[eid] = e_attrs.get("name", eid)
            enum_cases[eid] = e_attrs.get("cases", [])

        return types.SimpleNamespace(
            param_to_enum=param_to_enum,
            enum_name=enum_name,
            enum_cases=enum_cases,
            param_path=param_path,
            param_writeable=param_writeable,
        )

    def test_cc100_webserver_protocol_https_label(self) -> None:
        """CC100: webserver-protocol value=1 → label HTTPS."""
        plc = self._plc_from_cassettes("cc100")
        # The cassette has value=1 in the parameters page
        attrs = {"dataType": "enum_member", "value": 1}
        result = enrich_parameter(plc, "0-0-webserver-protocol", attrs)
        assert result["label"] == "HTTPS"
        assert result["enum_name"] == "WebserverTransferProtocols"

    def test_cc100_webserver_protocol_http_label(self) -> None:
        """CC100: webserver-protocol value=0 → label HTTP."""
        plc = self._plc_from_cassettes("cc100")
        attrs = {"dataType": "enum_member", "value": 0}
        result = enrich_parameter(plc, "0-0-webserver-protocol", attrs)
        assert result["label"] == "HTTP"

    def test_cc100_webserver_protocol_http_https_label(self) -> None:
        """CC100: webserver-protocol value=2 → label HTTP_HTTPS."""
        plc = self._plc_from_cassettes("cc100")
        attrs = {"dataType": "enum_member", "value": 2}
        result = enrich_parameter(plc, "0-0-webserver-protocol", attrs)
        assert result["label"] == "HTTP_HTTPS"

    def test_edge_container_runtime_docker_label(self) -> None:
        """Edge: container-runtime value=0 → label Docker."""
        plc = self._plc_from_cassettes("edge")
        attrs = {"dataType": "enum_member", "value": 0}
        result = enrich_parameter(plc, "0-0-edge-container-runtime", attrs)
        assert result["label"] == "Docker"
        assert result["enum_name"] == "ContainerRuntimes"

    def test_pfc200_fieldbus_protocol_profibus_label(self) -> None:
        """PFC200: fieldbus-protocol value=0 → label PROFIBUS."""
        plc = self._plc_from_cassettes("pfc200")
        attrs = {"dataType": "enum_member", "value": 0}
        result = enrich_parameter(plc, "0-0-fieldbus-protocol", attrs)
        assert result["label"] == "PROFIBUS"
        assert result["enum_name"] == "FieldbusProtocols"

    def test_path_attached_from_cassette(self) -> None:
        """enrich_parameter attaches the path derived from cassette definitions."""
        plc = self._plc_from_cassettes("cc100")
        attrs = {"dataType": "string", "value": "CC100-FAKESN001"}
        result = enrich_parameter(plc, "0-0-identity-hostname", attrs)
        assert result["path"] == "Identity/Hostname"

    def test_writeable_flag_from_cassette(self) -> None:
        """Writeable flag reflects parameter_definitions cassette."""
        plc = self._plc_from_cassettes("cc100")
        ro_attrs = {"dataType": "string", "value": "XXXX"}
        rw_attrs = {"dataType": "string", "value": "somehost"}
        assert enrich_parameter(plc, "0-0-identity-ordernumber", ro_attrs)["writeable"] is False
        assert enrich_parameter(plc, "0-0-identity-hostname", rw_attrs)["writeable"] is True


# ─────────────────────────── CT-06: invoke_method run responses ──────────────


class TestInvokeMethodRunResponses:
    """CT-06 — invoke_method returns the right data dict for each executionStatus."""

    async def test_done_returns_data_dict(self, cc100_run_done_router) -> None:
        client = _make_client(CC100_IP)
        try:
            result = await client.invoke_method("0-0-ntpclient-updatetime", {})
        finally:
            await client.close()

        assert result["attributes"]["executionStatus"] == "done"
        assert "outArgs" in result["attributes"]
        assert result["attributes"]["outArgs"]["result"]["value"] is True

    async def test_progress_returns_data_dict(self, cc100_run_progress_router) -> None:
        client = _make_client(CC100_IP)
        try:
            result = await client.invoke_method(
                "0-0-ntpclient-updatetime", {}, sync=False
            )
        finally:
            await client.close()

        assert result["attributes"]["executionStatus"] == "progress"

    async def test_error_returns_data_dict_with_code(self, cc100_run_error_router) -> None:
        client = _make_client(CC100_IP)
        try:
            result = await client.invoke_method("0-0-ntpclient-updatetime", {})
        finally:
            await client.close()

        assert result["attributes"]["executionStatus"] == "error"
        assert result["attributes"]["code"] == 26
        assert "NTP" in result["attributes"]["title"]

    async def test_inargs_wrapped_as_value_dict(self) -> None:
        """The POST body must wrap each inArg as {name: {'value': ...}} — not flat.

        Uses its own standalone respx.mock (no shared fixture) so the context
        manager is the sole active router and captures the POST request cleanly.
        """
        import httpx as _httpx
        import respx as _respx

        captured_request: list = []
        si = _load("cc100", "service_identity")
        run_cas = _load("cc100", "method_run_done")

        def _capture(request: _httpx.Request) -> _httpx.Response:
            captured_request.append(json.loads(request.content))
            return _httpx.Response(
                run_cas["status"],
                headers=run_cas.get("headers", {}),
                json=run_cas["body"],
            )

        with _respx.mock(assert_all_called=False) as router:
            router.get(f"https://{CC100_IP}/wda").mock(
                return_value=_httpx.Response(
                    si["status"],
                    headers=si["headers"],
                    json=si["body"],
                )
            )
            router.post(
                url__regex=rf"^https://10\.99\.99\.1/wda/methods/.+/runs.*$"
            ).mock(side_effect=_capture)

            client = _make_client(CC100_IP)
            try:
                await client.invoke_method(
                    "0-0-ntpclient-updatetime", {"server": "pool.ntp.org"}
                )
            finally:
                await client.close()

        assert len(captured_request) == 1, "POST to /runs was never captured"
        body = captured_request[0]
        in_args = body["data"]["attributes"]["inArgs"]
        # Each arg must be a dict with a "value" key — never a flat scalar.
        assert "server" in in_args
        assert isinstance(in_args["server"], dict)
        assert "value" in in_args["server"]
        assert in_args["server"]["value"] == "pool.ntp.org"


# ─────────────────────────── CT-07: stale-cassette guard ────────────────────


class TestStaleCassetteGuard:
    """CT-07 — Firmware comparator raises a clear re-record message when stale."""

    def _compare_firmware(self, cassette_fw: str, expected_fw: str, plc_class: str) -> None:
        """Raise AssertionError with a re-record message when firmware differs.

        This is the guard comparator TT5 will call after recording real cassettes.
        It is deliberately simple: exact string equality.  A future version could
        do semver ordering.
        """
        if cassette_fw != expected_fw:
            raise AssertionError(
                f"Cassette firmware '{cassette_fw}' != expected '{expected_fw}' "
                f"for class '{plc_class}'. Re-record from {plc_class} unit."
            )

    def test_matching_firmware_passes(self) -> None:
        # Should not raise.
        self._compare_firmware("03.09.10(99)", "03.09.10(99)", "cc100")

    def test_stale_firmware_raises_with_class_in_message(self) -> None:
        with pytest.raises(AssertionError) as exc_info:
            self._compare_firmware("03.09.08(12)", "03.09.10(99)", "cc100")
        msg = str(exc_info.value)
        assert "cc100" in msg
        assert "re-record" in msg.lower() or "Re-record" in msg

    def test_stale_message_contains_cassette_firmware(self) -> None:
        with pytest.raises(AssertionError) as exc_info:
            self._compare_firmware("03.09.08(12)", "03.09.10(99)", "cc100")
        assert "03.09.08(12)" in str(exc_info.value)

    def test_stale_message_contains_expected_firmware(self) -> None:
        with pytest.raises(AssertionError) as exc_info:
            self._compare_firmware("03.09.08(12)", "03.09.10(99)", "cc100")
        assert "03.09.10(99)" in str(exc_info.value)

    def test_meta_firmware_matches_service_identity(self) -> None:
        """The cc100 cassette _meta firmware must match the service_identity firmware."""
        si = _load("cc100", "service_identity")
        meta_fw = si["_meta"]["firmware"]
        body_fw = si["body"]["data"]["attributes"]["firmware"]
        self._compare_firmware(meta_fw, body_fw, "cc100")

    def test_edge_meta_firmware_matches_service_identity(self) -> None:
        si = _load("edge", "service_identity")
        meta_fw = si["_meta"]["firmware"]
        body_fw = si["body"]["data"]["attributes"]["firmware"]
        self._compare_firmware(meta_fw, body_fw, "edge")
