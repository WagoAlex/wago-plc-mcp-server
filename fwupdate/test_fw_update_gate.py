"""Regression: which authorization source fw_update actually consults.

This is the test that was missing. authz's own tests all passed while
fw_update never called load_ops_authorization at all, so a one-shot op with an
empty approved_by fell through to a standing fleet approval and flashed a
controller. The gate was correct; the wiring was not.
"""
import sys
import types

import pytest


@pytest.fixture
def fw(monkeypatch):
    monkeypatch.setenv("PLC_IP", "10.0.0.1")
    monkeypatch.setenv("PLC_PASSWORD", "x")
    for m in ("fw_update",):
        sys.modules.pop(m, None)
    import fw_update
    return fw_update


def _stub_authz(fw, monkeypatch, calls):
    stub = types.SimpleNamespace(
        NotAuthorized=fw.authz.NotAuthorized,
        load_ops_authorization=lambda *a, **k: (calls.append("ops"), ("opssha", "ALEX"))[1],
        load_policy=lambda *a, **k: (calls.append("policy"), ({}, "polsha"))[1],
        authorize=lambda *a, **k: ("polsha", ""),
    )
    monkeypatch.setattr(fw, "authz", stub)


def test_ops_file_replaces_the_fleet_policy(fw, monkeypatch):
    """With FW_OPS_FILE set, the fleet policy must never be consulted."""
    calls = []
    _stub_authz(fw, monkeypatch, calls)
    monkeypatch.setattr(fw, "FW_OPS_FILE", "/policy/ops/fw-1.yaml")
    monkeypatch.setattr(fw, "DRY_RUN", False)
    monkeypatch.setattr(fw, "FW_AUTHZ", True)
    monkeypatch.setattr(fw, "audit_record", lambda *a, **k: None)

    assert fw.check_authorization("4.9.1") == "opssha"
    assert calls == ["ops"], f"fleet policy must not be consulted, got {calls}"


def test_without_ops_file_the_fleet_policy_is_used(fw, monkeypatch):
    calls = []
    _stub_authz(fw, monkeypatch, calls)
    monkeypatch.setattr(fw, "FW_OPS_FILE", None)
    monkeypatch.setattr(fw, "DRY_RUN", False)
    monkeypatch.setattr(fw, "FW_AUTHZ", True)
    monkeypatch.setattr(fw, "audit_record", lambda *a, **k: None)

    assert fw.check_authorization("4.9.1") == "polsha"
    assert calls == ["policy"]


def test_a_refused_ops_file_never_falls_back(fw, monkeypatch):
    """The exact failure that flashed a live controller: an unsigned one-shot
    op must exit, not fall through to a standing approval for the same device."""
    calls = []

    def refuse(*a, **k):
        calls.append("ops")
        raise fw.authz.NotAuthorized("empty approved_by")

    stub = types.SimpleNamespace(
        NotAuthorized=fw.authz.NotAuthorized,
        load_ops_authorization=refuse,
        load_policy=lambda *a, **k: (calls.append("policy"), ({}, "polsha"))[1],
        authorize=lambda *a, **k: ("polsha", ""),
    )
    monkeypatch.setattr(fw, "authz", stub)
    monkeypatch.setattr(fw, "FW_OPS_FILE", "/policy/ops/fw-1.yaml")
    monkeypatch.setattr(fw, "DRY_RUN", False)
    monkeypatch.setattr(fw, "FW_AUTHZ", True)
    monkeypatch.setattr(fw, "audit_record", lambda *a, **k: None)

    with pytest.raises(SystemExit) as e:
        fw.check_authorization("4.9.1")
    assert e.value.code == 1
    assert calls == ["ops"], "must not consult the fleet policy after an ops refusal"
