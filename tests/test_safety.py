"""Unit tests for the safety gates and audit chain (no httpx, no live PLC)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from audit import GENESIS, build_entry, read_prev_hash  # noqa: E402
from safety import (  # noqa: E402
    compute_readonly_hosts,
    is_dangerous_method,
    parse_allowed_methods,
    parse_readonly_hosts,
)


def test_dangerous_methods_detected():
    assert is_dangerous_method("0-0-device-reboot")
    assert is_dangerous_method("0-0-Firmware-Update")  # case-insensitive
    assert is_dangerous_method("0-0-system-restart")
    assert is_dangerous_method("0-0-factoryreset")


def test_benign_methods_allowed():
    assert not is_dangerous_method("0-0-ntpclient-updatetime")
    assert not is_dangerous_method("0-0-snmp-reload")  # "reset" deliberately not in denylist
    assert not is_dangerous_method("")
    assert not is_dangerous_method("0-0-system-information")  # not "format"


def test_unicode_evasion_blocked():
    assert is_dangerous_method("0-0-re​boot")  # zero-width space folded out
    assert is_dangerous_method("0-0-rebootdevice")  # zero-separator


def test_compute_readonly_hosts(tmp_path, monkeypatch):
    fleet = tmp_path / "fleet.txt"
    fleet.write_text("1.1.1.1  # readonly line A\n2.2.2.2  # normal\n3.3.3.3\n")
    monkeypatch.setenv("WAGO_READONLY_HOSTS", "9.9.9.9")
    monkeypatch.setenv("WAGO_PLC_HOSTS_FILE", str(fleet))
    assert compute_readonly_hosts() == frozenset({"9.9.9.9", "1.1.1.1"})


def test_compute_readonly_hosts_missing_file_degrades(monkeypatch):
    monkeypatch.setenv("WAGO_READONLY_HOSTS", "9.9.9.9")
    monkeypatch.setenv("WAGO_PLC_HOSTS_FILE", "/nonexistent/fleet.txt")
    assert compute_readonly_hosts() == frozenset({"9.9.9.9"})


def test_csv_parsing():
    assert parse_readonly_hosts("1.2.3.4, 5.6.7.8 ,") == frozenset({"1.2.3.4", "5.6.7.8"})
    assert parse_allowed_methods("") == frozenset()
    assert parse_allowed_methods(None) == frozenset()


def test_audit_chain_links():
    line1, h1 = build_entry("set", "1.2.3.4", "agent", "ok", GENESIS, {})
    line2, h2 = build_entry("set", "1.2.3.4", "agent", "ok", h1, {})
    assert h1 != GENESIS and h2 != h1
    assert f'"prev": "{h1}"' in line2  # entry 2 chains off entry 1


def test_read_prev_hash_genesis_when_missing(tmp_path):
    assert read_prev_hash(str(tmp_path / "nope.log")) == GENESIS


def test_read_prev_hash_from_tail(tmp_path):
    log = tmp_path / "audit.log"
    line, h = build_entry("set", "1.2.3.4", "agent", "ok", GENESIS, {})
    log.write_text(line + "\n")
    assert read_prev_hash(str(log)) == h
