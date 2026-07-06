"""Unit tests for the tamper-evident audit chain (src/audit.py, src/audit_verify.py)."""
import hashlib
import json

from audit import GENESIS, REDACTED, append_audit, build_entry, read_prev_hash, redact_details
from audit_verify import verify


# ── chain construction ──

def test_build_entry_chains_hashes():
    line1, h1 = build_entry("set_parameters", "10.0.0.1", "agent", "ok", GENESIS, {})
    line2, h2 = build_entry("invoke_method", "10.0.0.1", "agent", "ok", h1, {})
    assert json.loads(line1)["prev"] == GENESIS
    assert json.loads(line2)["prev"] == h1
    assert h1 == hashlib.sha256(line1.encode()).hexdigest()
    assert h1 != h2


def test_read_prev_hash_missing_and_empty(tmp_path):
    assert read_prev_hash(str(tmp_path / "nope.log")) == GENESIS
    empty = tmp_path / "audit.log"
    empty.write_text("")
    assert read_prev_hash(str(empty)) == GENESIS


def test_read_prev_hash_rejects_partial_last_line(tmp_path):
    log = tmp_path / "audit.log"
    log.write_text('{"ts": "2026-01-01", "prev": "' + GENESIS + '"}\n{"truncat')
    assert read_prev_hash(str(log)) == GENESIS


def test_read_prev_hash_continues_chain(tmp_path):
    log = tmp_path / "audit.log"
    line = append_audit(str(log), "set_parameters", "10.0.0.1", "agent", "ok")
    assert read_prev_hash(str(log)) == hashlib.sha256(line.encode()).hexdigest()


# ── verification ──

def test_verify_passes_on_intact_chain(tmp_path):
    log = tmp_path / "audit.log"
    for i in range(5):
        append_audit(str(log), "set_parameters", "10.0.0.1", "agent", f"ok-{i}")
    assert verify(str(log)) is True


def test_verify_fails_on_tampered_entry(tmp_path):
    log = tmp_path / "audit.log"
    for i in range(5):
        append_audit(str(log), "set_parameters", "10.0.0.1", "agent", f"ok-{i}")
    lines = log.read_text().splitlines()
    doctored = json.loads(lines[2])
    doctored["result"] = "tampered"
    lines[2] = json.dumps(doctored)
    log.write_text("\n".join(lines) + "\n")
    assert verify(str(log)) is False


# ── redaction (#22) ──

def test_redacts_sensitive_parameter_values():
    details = {"params": [
        {"id": "0-0-snmp-communities-1-name", "value": "s3cret-community"},
        {"id": "0-0-ntpclient-updateinterval", "value": 300},
    ]}
    out = redact_details(details)
    assert out["params"][0]["value"] == REDACTED
    assert out["params"][1]["value"] == 300
    # input not mutated
    assert details["params"][0]["value"] == "s3cret-community"


def test_redacts_sensitive_method_args():
    out = redact_details({"args": {"password": "hunter2", "hostname": "plc1"}})
    assert out["args"]["password"] == REDACTED
    assert out["args"]["hostname"] == "plc1"


def test_build_entry_redacts_before_hashing():
    line, h = build_entry(
        "set_parameters", "10.0.0.1", "agent", "ok", GENESIS,
        {"params": [{"id": "0-0-openvpn-password", "value": "vpn-secret"}]},
    )
    assert "vpn-secret" not in line
    # chain hash covers the stored (redacted) line
    assert h == hashlib.sha256(line.encode()).hexdigest()
