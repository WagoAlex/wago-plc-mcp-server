"""Unit tests for src/gitops.py - pure functions, no I/O, no mocks."""
import yaml
import pytest
from gitops import (
    desired_state_fragment,
    ops_fragment,
    cloud_params,
    ntp_params,
    snmp_params,
    serial_params,
    openvpn_params,
    browser_params,
)


# ---------------------------------------------------------------------------
# desired_state_fragment (non-critical path)
# ---------------------------------------------------------------------------

def test_desired_state_fragment_shape():
    params = [{"id": "0-0-ntpclient-enabled", "value": True}]
    result = desired_state_fragment("192.168.42.110", params)

    assert result["status"] == "proposed"
    assert result["config_file"] == "plcs/192.168.42.110.yaml"
    assert "desired_state_yaml" in result
    assert "next_step" in result


def test_desired_state_fragment_yaml_roundtrip():
    params = [
        {"id": "0-0-ntpclient-enabled", "value": True},
        {"id": "0-0-snmp-enable", "value": False},
    ]
    result = desired_state_fragment("192.168.42.118", params)
    data = yaml.safe_load(result["desired_state_yaml"])

    assert data["plc_ip"] == "192.168.42.118"
    assert data["managed_parameters"]["0-0-ntpclient-enabled"] is True
    assert data["managed_parameters"]["0-0-snmp-enable"] is False


def test_desired_state_fragment_config_file_matches_ip():
    result = desired_state_fragment("10.0.0.1", [{"id": "x", "value": 1}])
    assert result["config_file"] == "plcs/10.0.0.1.yaml"


def test_desired_state_fragment_default_repo_in_next_step():
    result = desired_state_fragment("192.168.42.110", [{"id": "x", "value": 1}])
    assert "wago-plc-config/plcs/192.168.42.110.yaml" in result["next_step"]


def test_desired_state_fragment_custom_repo_in_next_step():
    result = desired_state_fragment("192.168.42.110", [{"id": "x", "value": 1}], repo="acme/plc-fleet-config")
    assert "acme/plc-fleet-config/plcs/192.168.42.110.yaml" in result["next_step"]
    assert "wago-plc-config" not in result["next_step"]


# ---------------------------------------------------------------------------
# ops_fragment - non-critical (no dangerous flag)
# ---------------------------------------------------------------------------

def test_ops_fragment_non_critical_shape():
    result = ops_fragment("192.168.42.110", "0-0-ntpclient-updatetime", {}, "agent-test")

    assert result["status"] == "proposed"
    assert result["config_file"].startswith("ops/")
    assert result["config_file"].endswith(".yaml")
    assert "ops_yaml" in result
    assert "warning" not in result


def test_ops_fragment_non_critical_no_gate_fields():
    result = ops_fragment("192.168.42.110", "0-0-ntpclient-updatetime", {}, "agent-test")
    data = yaml.safe_load(result["ops_yaml"])

    assert "requires_human" not in data
    assert "approved_by" not in data


def test_ops_fragment_non_critical_yaml_content():
    args = {"key": "val"}
    result = ops_fragment("192.168.42.110", "0-0-ntpclient-updatetime", args, "agent-1")
    data = yaml.safe_load(result["ops_yaml"])

    assert data["plc_ip"] == "192.168.42.110"
    assert data["method_id"] == "0-0-ntpclient-updatetime"
    assert data["arguments"] == args
    assert data["proposed_by"] == "agent-1"
    assert data["action"] == "invoke_method"
    assert len(data["id"]) == 8  # uuid4 hex[:8]


def test_ops_fragment_custom_repo_in_next_step():
    result = ops_fragment("192.168.42.110", "0-0-ntpclient-updatetime", {}, "agent-test", repo="acme/plc-fleet-config")
    assert "acme/plc-fleet-config/ops/" in result["next_step"]
    assert "wago-plc-config" not in result["next_step"]


# ---------------------------------------------------------------------------
# ops_fragment - critical (dangerous=True)
# ---------------------------------------------------------------------------

def test_ops_fragment_critical_has_warning():
    result = ops_fragment("192.168.42.110", "0-0-device-reboot", {}, "agent-test", dangerous=True)
    assert "warning" in result
    assert "CRITICAL" in result["warning"]


def test_ops_fragment_critical_gate_fields():
    result = ops_fragment("192.168.42.110", "0-0-device-reboot", {}, "agent-test", dangerous=True)
    data = yaml.safe_load(result["ops_yaml"])

    assert data["requires_human"] == "CRITICAL"
    assert data["approved_by"] == ""  # must be empty - human fills this during PR review


def test_ops_fragment_critical_approved_by_is_empty_string():
    # Verify the agent never pre-fills approved_by - that would defeat the gate.
    result = ops_fragment("192.168.42.110", "0-0-firmware-update", {}, "agent-test", dangerous=True)
    data = yaml.safe_load(result["ops_yaml"])
    assert data["approved_by"] == ""


# ---------------------------------------------------------------------------
# ops_fragment - unique IDs per call
# ---------------------------------------------------------------------------

def test_ops_fragment_unique_ids():
    r1 = ops_fragment("192.168.42.110", "0-0-ntpclient-updatetime", {}, "a")
    r2 = ops_fragment("192.168.42.110", "0-0-ntpclient-updatetime", {}, "a")
    assert r1["config_file"] != r2["config_file"]


# ---------------------------------------------------------------------------
# Parameter builder smoke tests - check IDs are present
# ---------------------------------------------------------------------------

def test_cloud_params_ids():
    result = cloud_params("my-client", "mqtt.example.com")
    ids = {p["id"] for p in result}
    assert "0-0-cloudconnections-1-transport-host" in ids
    assert "0-0-cloudconnections-1-enabled" in ids
    assert any(p["value"] == "mqtt.example.com" for p in result)


def test_ntp_params_ids():
    result = ntp_params(["192.168.1.1", "192.168.1.2"])
    ids = {p["id"] for p in result}
    assert "0-0-ntpclient-enabled" in ids
    assert "0-0-ntpclient-configuredtimeservers" in ids


def test_snmp_params_ids():
    result = snmp_params(enabled=True, community="public")
    ids = {p["id"] for p in result}
    assert "0-0-snmp-enable" in ids
    assert "0-0-snmp-communities-1-name" in ids


def test_serial_params_no_owner():
    result = serial_params(assigned_mode=1)
    assert len(result) == 1
    assert result[0]["id"] == "0-0-serialinterfaces-1-assignedmode"


def test_serial_params_with_owner():
    result = serial_params(assigned_mode=2, assigned_owner=1)
    ids = [p["id"] for p in result]
    assert "0-0-serialinterfaces-1-assignedowner" in ids


def test_openvpn_params_ids():
    result = openvpn_params(enabled=False)
    ids = {p["id"] for p in result}
    assert "0-0-openvpn-enabled" in ids


def test_browser_params_ids():
    result = browser_params()
    ids = {p["id"] for p in result}
    assert "0-0-integratedwebbrowser-startpage" in ids
