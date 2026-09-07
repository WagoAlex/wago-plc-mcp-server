"""Audit records must reach an external collector, and a dead collector must
never break a PLC operation."""
import importlib
import json
import socket

import pytest


@pytest.fixture
def audit(monkeypatch):
    """Fresh module each time - the handler is cached in module state."""
    import audit as audit_mod
    importlib.reload(audit_mod)
    yield audit_mod
    importlib.reload(audit_mod)


def _udp_listener():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.1", 0))
    s.settimeout(3)
    return s, s.getsockname()[1]


def test_firmware_record_reaches_the_collector(audit, monkeypatch, tmp_path):
    sock, port = _udp_listener()
    monkeypatch.setenv("AUDIT_SYSLOG", f"udp://127.0.0.1:{port}")

    audit.append_audit(str(tmp_path / "audit.log"), "firmware_update", "10.0.0.1",
                       "fwupdate", "ok", revision="4.9.1", approved_by="ALEX")

    datagram = sock.recv(8192).decode()
    sock.close()
    assert "wago-plc-audit" in datagram
    payload = json.loads(datagram[datagram.index("{"):])
    assert payload["action"] == "firmware_update"
    assert payload["approved_by"] == "ALEX"
    assert payload["prev"] == audit.GENESIS


def test_bare_host_port_is_accepted(audit, monkeypatch, tmp_path):
    sock, port = _udp_listener()
    monkeypatch.setenv("AUDIT_SYSLOG", f"127.0.0.1:{port}")
    audit.append_audit(str(tmp_path / "audit.log"), "set_parameters", "10.0.0.1", "k", "ok")
    assert "set_parameters" in sock.recv(8192).decode()
    sock.close()


def test_unreachable_collector_does_not_break_the_write(audit, monkeypatch, tmp_path):
    """The on-disk chain is authoritative; syslog is a second copy."""
    monkeypatch.setenv("AUDIT_SYSLOG", "tcp://127.0.0.1:9")  # discard port, refuses TCP
    log = tmp_path / "audit.log"
    audit.append_audit(str(log), "firmware_update", "10.0.0.1", "fwupdate", "ok")
    assert json.loads(log.read_text().splitlines()[0])["action"] == "firmware_update"


def test_unconfigured_is_a_no_op(audit, monkeypatch, tmp_path):
    monkeypatch.delenv("AUDIT_SYSLOG", raising=False)
    log = tmp_path / "audit.log"
    audit.append_audit(str(log), "firmware_update", "10.0.0.1", "fwupdate", "ok")
    assert log.read_text().count("\n") == 1


def test_passwords_are_redacted_before_forwarding(audit, monkeypatch, tmp_path):
    sock, port = _udp_listener()
    monkeypatch.setenv("AUDIT_SYSLOG", f"udp://127.0.0.1:{port}")
    audit.append_audit(str(tmp_path / "audit.log"), "firmware_update", "10.0.0.1",
                       "fwupdate", "ok", plc_password="hunter2")
    datagram = sock.recv(8192).decode()
    sock.close()
    assert "hunter2" not in datagram
