"""Unit tests for scripts/apply.py - reconciler logic with mocked WDAClient.

WDAClient is mocked at the class level so no network I/O occurs.
All tests are CI-safe (no `live` or `mutate` markers).
"""
import os
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import apply


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_client(get_value=None, set_ok=True, invoke_result=None):
    """Return a mock WDAClient instance."""
    client = MagicMock()
    client.close = AsyncMock()

    if get_value is not None:
        client.get_parameter = AsyncMock(return_value={"value": get_value})
    if set_ok:
        client.set_parameters = AsyncMock(return_value=None)
    if invoke_result is not None:
        client.invoke_method = AsyncMock(return_value=invoke_result)

    return client


def _patch_client(monkeypatch, mock_client):
    """Patch apply._client so the reconciler functions receive mock_client."""
    # _client() returns the WDAClient class; the functions call WDAClient(ip, user, pass, timeout=).
    # We replace _client with a factory that returns a callable producing mock_client.
    monkeypatch.setattr("apply._client", lambda: lambda *a, **kw: mock_client)


# ---------------------------------------------------------------------------
# apply_desired_state - non-critical path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_no_drift_returns_0(monkeypatch):
    """When PLC already has the desired value, nothing is patched."""
    mock_client = _make_client(get_value=True)
    _patch_client(monkeypatch, mock_client)
    monkeypatch.setenv("WAGO_READONLY_HOSTS", "")

    data = {"plc_ip": "192.168.42.110", "managed_parameters": {"0-0-ntpclient-enabled": True}}
    rc = await apply.apply_desired_state(data, execute=False)

    assert rc == 0
    mock_client.set_parameters.assert_not_called()


@pytest.mark.asyncio
async def test_drift_dry_run_no_patch(monkeypatch):
    """Drift detected but --execute not set - no PATCH is sent."""
    mock_client = _make_client(get_value=False)  # PLC has False, desired is True
    _patch_client(monkeypatch, mock_client)
    monkeypatch.setenv("WAGO_READONLY_HOSTS", "")

    data = {"plc_ip": "192.168.42.110", "managed_parameters": {"0-0-ntpclient-enabled": True}}
    rc = await apply.apply_desired_state(data, execute=False)

    assert rc == 0
    mock_client.set_parameters.assert_not_called()


@pytest.mark.asyncio
async def test_drift_execute_patches_only_drifted(monkeypatch):
    """With --execute, only the drifted parameter is PATCHed."""
    # First param drifts, second is already correct.
    call_count = 0

    async def get_param(param_id):
        nonlocal call_count
        call_count += 1
        # ntpclient-enabled: PLC=False, desired=True  -> drift
        # snmp-enable: PLC=False, desired=False        -> in sync
        if "ntpclient-enabled" in param_id:
            return {"value": False}
        return {"value": False}

    mock_client = _make_client()
    mock_client.get_parameter = get_param
    _patch_client(monkeypatch, mock_client)
    monkeypatch.setenv("WAGO_READONLY_HOSTS", "")

    data = {
        "plc_ip": "192.168.42.110",
        "managed_parameters": {
            "0-0-ntpclient-enabled": True,   # drifts
            "0-0-snmp-enable": False,         # already correct
        },
    }
    rc = await apply.apply_desired_state(data, execute=True)

    assert rc == 0
    mock_client.set_parameters.assert_called_once()
    patches = mock_client.set_parameters.call_args[0][0]
    patched_ids = [p["id"] for p in patches]
    assert "0-0-ntpclient-enabled" in patched_ids
    assert "0-0-snmp-enable" not in patched_ids


@pytest.mark.asyncio
async def test_readonly_host_blocks_desired_state(monkeypatch):
    """A read-only PLC is refused before any WDA call."""
    mock_client = _make_client(get_value=True)
    _patch_client(monkeypatch, mock_client)
    monkeypatch.setenv("WAGO_READONLY_HOSTS", "192.168.42.110")

    data = {"plc_ip": "192.168.42.110", "managed_parameters": {"0-0-snmp-enable": False}}
    rc = await apply.apply_desired_state(data, execute=True)

    assert rc == 1
    mock_client.set_parameters.assert_not_called()


# ---------------------------------------------------------------------------
# apply_ops - critical path (dangerous method gate)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_non_dangerous_op_executes(monkeypatch, tmp_path):
    """A safe method (no dangerous roots) is invoked directly, ops file deleted."""
    mock_client = _make_client(invoke_result={"status": "ok"})
    _patch_client(monkeypatch, mock_client)
    monkeypatch.setenv("WAGO_READONLY_HOSTS", "")
    monkeypatch.delenv("WAGO_APPROVED_BY", raising=False)

    ops_file = tmp_path / "op.yaml"
    ops_file.write_text("")  # content not read by apply_ops directly

    data = {
        "plc_ip": "192.168.42.110",
        "method_id": "0-0-ntpclient-updatetime",
        "arguments": {},
        "proposed_by": "agent-test",
        "approved_by": "",
    }
    rc = await apply.apply_ops(data, ops_file, execute=True)

    assert rc == 0
    assert not ops_file.exists()
    mock_client.invoke_method.assert_called_once()


@pytest.mark.asyncio
async def test_dangerous_op_refused_without_approved_by(monkeypatch, tmp_path):
    """Dangerous method with empty approved_by is refused - gate must hold."""
    mock_client = _make_client(invoke_result={"status": "ok"})
    _patch_client(monkeypatch, mock_client)
    monkeypatch.setenv("WAGO_READONLY_HOSTS", "")
    monkeypatch.delenv("WAGO_APPROVED_BY", raising=False)

    ops_file = tmp_path / "reboot.yaml"
    ops_file.write_text("")

    data = {
        "plc_ip": "192.168.42.110",
        "method_id": "0-0-device-reboot",
        "arguments": {},
        "proposed_by": "agent-test",
        "approved_by": "",  # not filled
    }
    rc = await apply.apply_ops(data, ops_file, execute=True)

    assert rc == 1
    assert ops_file.exists()  # file not deleted - op was refused
    mock_client.invoke_method.assert_not_called()


@pytest.mark.asyncio
async def test_dangerous_op_allowed_with_approved_by_env(monkeypatch, tmp_path):
    """Dangerous method with WAGO_APPROVED_BY set via env is allowed through."""
    mock_client = _make_client(invoke_result={"status": "ok"})
    _patch_client(monkeypatch, mock_client)
    monkeypatch.setenv("WAGO_READONLY_HOSTS", "")
    monkeypatch.setenv("WAGO_APPROVED_BY", "alice@example.com")

    ops_file = tmp_path / "reboot.yaml"
    ops_file.write_text("")

    data = {
        "plc_ip": "192.168.42.110",
        "method_id": "0-0-device-reboot",
        "arguments": {},
        "proposed_by": "agent-test",
        "approved_by": "",
    }
    rc = await apply.apply_ops(data, ops_file, execute=True)

    assert rc == 0
    assert not ops_file.exists()
    mock_client.invoke_method.assert_called_once()


@pytest.mark.asyncio
async def test_dangerous_op_allowed_with_approved_by_in_yaml(monkeypatch, tmp_path):
    """Dangerous method with approved_by set in the YAML (human filled it) is allowed."""
    mock_client = _make_client(invoke_result={"status": "ok"})
    _patch_client(monkeypatch, mock_client)
    monkeypatch.setenv("WAGO_READONLY_HOSTS", "")
    monkeypatch.delenv("WAGO_APPROVED_BY", raising=False)

    ops_file = tmp_path / "reboot.yaml"
    ops_file.write_text("")

    data = {
        "plc_ip": "192.168.42.110",
        "method_id": "0-0-device-reboot",
        "arguments": {},
        "proposed_by": "agent-test",
        "approved_by": "bob@example.com",  # human set this during PR review
    }
    rc = await apply.apply_ops(data, ops_file, execute=True)

    assert rc == 0
    mock_client.invoke_method.assert_called_once()


@pytest.mark.asyncio
async def test_dangerous_op_dry_run_no_invoke(monkeypatch, tmp_path):
    """Dangerous op with valid approval but no --execute does not invoke."""
    mock_client = _make_client(invoke_result={"status": "ok"})
    _patch_client(monkeypatch, mock_client)
    monkeypatch.setenv("WAGO_READONLY_HOSTS", "")
    monkeypatch.setenv("WAGO_APPROVED_BY", "alice@example.com")

    ops_file = tmp_path / "reboot.yaml"
    ops_file.write_text("")

    data = {
        "plc_ip": "192.168.42.110",
        "method_id": "0-0-device-reboot",
        "arguments": {},
        "proposed_by": "agent-test",
        "approved_by": "",
    }
    rc = await apply.apply_ops(data, ops_file, execute=False)

    assert rc == 0
    assert ops_file.exists()  # not deleted - dry-run
    mock_client.invoke_method.assert_not_called()


@pytest.mark.asyncio
async def test_readonly_host_blocks_ops(monkeypatch, tmp_path):
    """A read-only PLC blocks ops regardless of approval status."""
    mock_client = _make_client(invoke_result={"status": "ok"})
    _patch_client(monkeypatch, mock_client)
    monkeypatch.setenv("WAGO_READONLY_HOSTS", "192.168.42.110")
    monkeypatch.setenv("WAGO_APPROVED_BY", "alice@example.com")

    ops_file = tmp_path / "op.yaml"
    ops_file.write_text("")

    data = {
        "plc_ip": "192.168.42.110",
        "method_id": "0-0-device-reboot",
        "arguments": {},
        "proposed_by": "agent-test",
        "approved_by": "alice@example.com",
    }
    rc = await apply.apply_ops(data, ops_file, execute=True)

    assert rc == 1
    mock_client.invoke_method.assert_not_called()
