"""Unit tests for scripts/apply.py - reconciler logic with mocked WDAClient.

WDAClient is mocked at the class level so no network I/O occurs.
All tests are CI-safe (no `live` or `mutate` markers).
"""
import os
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import yaml
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


# --- firmware ops files: same lifecycle and gates as a reboot ----------------

def _fw_ops(tmp_path, approved_by="", target_version="4.9.1", ip="10.0.0.1"):
    p = tmp_path / "fw-test.yaml"
    p.write_text(
        f"id: fw-test\nplc_ip: {ip}\naction: firmware_update\n"
        f"target_version: '{target_version}'\nrequires_human: CRITICAL\n"
        f"approved_by: '{approved_by}'\n"
    )
    return p


def test_firmware_ops_without_approved_by_is_refused(tmp_path, monkeypatch, capsys):
    from apply import apply_firmware
    monkeypatch.delenv("WAGO_APPROVED_BY", raising=False)
    monkeypatch.delenv("WAGO_READONLY_HOSTS", raising=False)
    p = _fw_ops(tmp_path)
    data = yaml.safe_load(p.read_text())

    assert apply_firmware(data, p, execute=True) == 1
    assert "no `approved_by`" in capsys.readouterr().err
    assert p.exists(), "a refused op must not be deleted"


def test_firmware_ops_without_target_version_is_refused(tmp_path, monkeypatch):
    from apply import apply_firmware
    monkeypatch.setenv("WAGO_APPROVED_BY", "ALEX")
    p = tmp_path / "fw-bad.yaml"
    p.write_text("id: fw-bad\nplc_ip: 10.0.0.1\naction: firmware_update\napproved_by: 'ALEX'\n")
    assert apply_firmware(yaml.safe_load(p.read_text()), p, execute=True) == 1


def test_firmware_ops_dry_run_never_touches_the_device(tmp_path, monkeypatch, capsys):
    """A PR check must not upload 200 MB to a controller."""
    from apply import apply_firmware
    monkeypatch.setenv("WAGO_APPROVED_BY", "ALEX")
    called = []
    monkeypatch.setattr("apply.subprocess.run", lambda *a, **k: called.append(a) or None)
    p = _fw_ops(tmp_path, approved_by="ALEX")

    assert apply_firmware(yaml.safe_load(p.read_text()), p, execute=False) == 0
    assert not called, "dry-run must not invoke the flash tool"
    assert p.exists()
    assert "Dry-run" in capsys.readouterr().out


def test_firmware_ops_readonly_host_is_refused(tmp_path, monkeypatch):
    from apply import apply_firmware
    monkeypatch.setenv("WAGO_APPROVED_BY", "ALEX")
    monkeypatch.setenv("WAGO_READONLY_HOSTS", "10.0.0.1")
    p = _fw_ops(tmp_path, approved_by="ALEX")
    assert apply_firmware(yaml.safe_load(p.read_text()), p, execute=True) == 1
    assert p.exists()


def test_failed_flash_keeps_the_ops_file_for_retry(tmp_path, monkeypatch):
    from apply import apply_firmware

    class R:
        returncode = 1

    monkeypatch.setenv("WAGO_APPROVED_BY", "ALEX")
    monkeypatch.delenv("WAGO_READONLY_HOSTS", raising=False)
    monkeypatch.setattr("apply.subprocess.run", lambda *a, **k: R())
    tool = tmp_path / "fw_update.py"; tool.write_text("")
    monkeypatch.setenv("FWUPDATE_TOOL", str(tool))
    p = _fw_ops(tmp_path, approved_by="ALEX")

    assert apply_firmware(yaml.safe_load(p.read_text()), p, execute=True) == 1
    assert p.exists(), "a failed flash must leave the op in place"


def test_successful_flash_deletes_the_ops_file(tmp_path, monkeypatch):
    from apply import apply_firmware

    class R:
        returncode = 0

    monkeypatch.setenv("WAGO_APPROVED_BY", "ALEX")
    monkeypatch.delenv("WAGO_READONLY_HOSTS", raising=False)
    monkeypatch.setattr("apply.subprocess.run", lambda *a, **k: R())
    tool = tmp_path / "fw_update.py"; tool.write_text("")
    monkeypatch.setenv("FWUPDATE_TOOL", str(tool))
    p = _fw_ops(tmp_path, approved_by="ALEX")

    assert apply_firmware(yaml.safe_load(p.read_text()), p, execute=True) == 0
    assert not p.exists(), "a completed op is deleted, like a reboot"


def test_allow_reflash_is_declared_in_the_yaml_not_the_environment(tmp_path, monkeypatch):
    """Writing the version a device already runs must be visible to a reviewer."""
    from apply import apply_firmware
    captured = {}

    class R:
        returncode = 0

    def fake_run(cmd, env=None, **k):
        captured.update(env or {})
        return R()

    monkeypatch.setenv("WAGO_APPROVED_BY", "ALEX")
    monkeypatch.delenv("WAGO_READONLY_HOSTS", raising=False)
    monkeypatch.setattr("apply.subprocess.run", fake_run)
    tool = tmp_path / "fw_update.py"; tool.write_text("")
    monkeypatch.setenv("FWUPDATE_TOOL", str(tool))

    p = tmp_path / "fw.yaml"
    p.write_text("id: fw\nplc_ip: 10.0.0.1\naction: firmware_update\n"
                 "target_version: '4.9.1'\napproved_by: 'ALEX'\nallow_reflash: true\n")
    assert apply_firmware(yaml.safe_load(p.read_text()), p, execute=True) == 0
    assert captured["FW_ALLOW_REFLASH"] == "true"
    assert captured["FW_OPS_FILE"] == str(p.resolve())

    p2 = tmp_path / "fw2.yaml"
    p2.write_text("id: fw2\nplc_ip: 10.0.0.1\naction: firmware_update\n"
                  "target_version: '4.9.1'\napproved_by: 'ALEX'\n")
    assert apply_firmware(yaml.safe_load(p2.read_text()), p2, execute=True) == 0
    assert captured["FW_ALLOW_REFLASH"] == "false"
