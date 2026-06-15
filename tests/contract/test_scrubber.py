"""Unit tests for the scrub() helper in tests/tools/record_cassettes.py.

No network, no Docker secrets, no PLC required.
"""
from __future__ import annotations

import pytest

from tests.tools.record_cassettes import scrub

_REDACTED = "REDACTED"


# ─────────────────────────── basic scrub cases ──────────────────────────────


class TestScrubKeys:
    """Sensitive key names must have their values replaced with REDACTED."""

    def test_password_key_scrubbed(self) -> None:
        result = scrub({"password": "SuperSecret123"})
        assert result["password"] == _REDACTED

    def test_token_key_scrubbed(self) -> None:
        result = scrub({"WAGO-WDX-Auth-Token": "eyJhbGciOiJIUzI1NiJ9.fake"})
        assert result["WAGO-WDX-Auth-Token"] == _REDACTED

    def test_serial_key_scrubbed(self) -> None:
        result = scrub({"serialNumber": "SN-1234567890"})
        assert result["serialNumber"] == _REDACTED

    def test_ordernumber_key_scrubbed(self) -> None:
        result = scrub({"orderNumber": "750-8101/025-000"})
        assert result["orderNumber"] == _REDACTED

    def test_order_number_underscore_key_scrubbed(self) -> None:
        result = scrub({"order_number": "750-8101/025-000"})
        assert result["order_number"] == _REDACTED

    def test_hostname_key_scrubbed(self) -> None:
        result = scrub({"hostname": "CC100-ABC123DEF456"})
        assert result["hostname"] == _REDACTED

    def test_authorization_key_scrubbed(self) -> None:
        result = scrub({"Authorization": "Basic YWRtaW46d2Fnbw=="})
        assert result["Authorization"] == _REDACTED

    def test_case_insensitive_password(self) -> None:
        result = scrub({"PASSWORD": "topsecret", "Password": "also_secret"})
        assert result["PASSWORD"] == _REDACTED
        assert result["Password"] == _REDACTED

    def test_non_sensitive_key_preserved(self) -> None:
        result = scrub({"dataType": "string", "value": "hello"})
        assert result["dataType"] == "string"
        assert result["value"] == "hello"


class TestScrubBearerValues:
    """Strings that look like JWT bearer tokens must be scrubbed regardless of key."""

    def test_bearer_jwt_value_scrubbed(self) -> None:
        result = scrub({"arbitrary_key": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.payload"})
        assert result["arbitrary_key"] == _REDACTED

    def test_non_jwt_string_preserved(self) -> None:
        result = scrub({"some_key": "not_a_token"})
        assert result["some_key"] == "not_a_token"

    def test_short_ey_string_preserved(self) -> None:
        """Short 'ey' strings (< 10 chars after ey) must not be redacted."""
        result = scrub({"key": "ey12345"})
        assert result["key"] == "ey12345"


class TestScrubRecursion:
    """Scrub must descend into nested dicts and lists."""

    def test_nested_dict_scrubbed(self) -> None:
        blob = {
            "data": {
                "attributes": {
                    "hostname": "CC100-REALSERIAL",
                    "firmware": "03.09.10(99)",
                }
            }
        }
        result = scrub(blob)
        assert result["data"]["attributes"]["hostname"] == _REDACTED
        assert result["data"]["attributes"]["firmware"] == "03.09.10(99)"

    def test_list_of_dicts_scrubbed(self) -> None:
        blob = [
            {"password": "abc", "value": 1},
            {"password": "def", "value": 2},
        ]
        result = scrub(blob)
        assert result[0]["password"] == _REDACTED
        assert result[0]["value"] == 1
        assert result[1]["password"] == _REDACTED

    def test_deeply_nested_structure(self) -> None:
        blob = {
            "a": {
                "b": {
                    "c": {
                        "orderNumber": "750-8101/025-000",
                        "safe": "keep"
                    }
                }
            }
        }
        result = scrub(blob)
        assert result["a"]["b"]["c"]["orderNumber"] == _REDACTED
        assert result["a"]["b"]["c"]["safe"] == "keep"

    def test_list_inside_dict_scrubbed(self) -> None:
        blob = {"items": [{"hostname": "PLC-XYZ"}, {"hostname": "PLC-ABC"}]}
        result = scrub(blob)
        assert result["items"][0]["hostname"] == _REDACTED
        assert result["items"][1]["hostname"] == _REDACTED


class TestScrubImmutability:
    """scrub() must not mutate the input."""

    def test_input_dict_not_mutated(self) -> None:
        original = {"password": "secret", "value": 42}
        original_copy = dict(original)
        scrub(original)
        assert original == original_copy

    def test_input_list_not_mutated(self) -> None:
        original = [{"password": "secret"}]
        scrub(original)
        assert original[0]["password"] == "secret"

    def test_nested_input_not_mutated(self) -> None:
        original = {"data": {"attributes": {"hostname": "real-hostname"}}}
        scrub(original)
        assert original["data"]["attributes"]["hostname"] == "real-hostname"


class TestScrubScalars:
    """Scalar values (int, float, bool, None) pass through unchanged."""

    def test_integer_unchanged(self) -> None:
        assert scrub(42) == 42

    def test_none_unchanged(self) -> None:
        assert scrub(None) is None

    def test_bool_unchanged(self) -> None:
        assert scrub(True) is True

    def test_float_unchanged(self) -> None:
        assert scrub(3.14) == 3.14


class TestScrubRealBlob:
    """Simulate a real WDA service-identity response and verify the result."""

    def test_full_service_identity_blob(self) -> None:
        blob = {
            "data": {
                "id": "wda",
                "type": "service-identities",
                "attributes": {
                    "name": "WDA",
                    "version": "1.4.1",
                    "firmware": "03.09.10(99)",
                    "hostname": "CC100-REALSERIAL001",
                    "orderNumber": "750-8101/025-000",
                },
            }
        }
        result = scrub(blob)
        # sensitive fields scrubbed
        assert result["data"]["attributes"]["hostname"] == _REDACTED
        assert result["data"]["attributes"]["orderNumber"] == _REDACTED
        # non-sensitive fields preserved
        assert result["data"]["attributes"]["firmware"] == "03.09.10(99)"
        assert result["data"]["attributes"]["version"] == "1.4.1"
        assert result["data"]["attributes"]["name"] == "WDA"
        # structure preserved
        assert result["data"]["id"] == "wda"
        assert result["data"]["type"] == "service-identities"

    def test_headers_blob_with_token(self) -> None:
        blob = {
            "content-type": "application/vnd.api+json",
            "WAGO-WDX-Auth-Token": "eyJhbGciOiJIUzI1NiJ9.REAL_TOKEN_VALUE",
            "WAGO-WDX-Auth-Token-Type": "Bearer",
            "WAGO-WDX-Auth-Token-Expiration": "300",
        }
        result = scrub(blob)
        # Keys containing "token" are scrubbed (case-insensitive pattern).
        assert result["WAGO-WDX-Auth-Token"] == _REDACTED
        assert result["WAGO-WDX-Auth-Token-Type"] == _REDACTED
        assert result["WAGO-WDX-Auth-Token-Expiration"] == _REDACTED
        # content-type is safe (does not match any sensitive pattern).
        assert result["content-type"] == "application/vnd.api+json"
