"""Unit tests for the safety gates (src/safety.py)."""
import pytest

from safety import (
    compute_readonly_hosts,
    is_dangerous_method,
    parse_allowed_methods,
    parse_readonly_hosts,
)


@pytest.mark.parametrize("mid", [
    "0-0-reboot",
    "0-0-restart-network",
    "0-0-factoryreset",
    "0-0-factory-reset",
    "0-0-firmware-update",
    "0-0-firmwareupdate",
    "0-0-sdcard-format",
    "re​boot",  # zero-width char must not split the dangerous word
])
def test_dangerous_methods_detected(mid):
    assert is_dangerous_method(mid)


@pytest.mark.parametrize("mid", [
    "0-0-ntpclient-updatetime",
    "0-0-information-status",   # "format" inside "information" must NOT hit
    "0-0-resettable-counter",   # bare "reset" root deliberately not listed
    "",
])
def test_benign_methods_pass(mid):
    assert not is_dangerous_method(mid)


def test_parse_allowed_methods():
    allowed = parse_allowed_methods(" 0-0-reboot , 0-0-firmware-update ,")
    assert allowed == frozenset({"0-0-reboot", "0-0-firmware-update"})
    assert parse_allowed_methods(None) == frozenset()


def test_parse_readonly_hosts():
    assert parse_readonly_hosts("10.0.0.1,10.0.0.2") == frozenset({"10.0.0.1", "10.0.0.2"})


def test_compute_readonly_hosts_merges_env_and_fleet_file(monkeypatch, tmp_path):
    fleet = tmp_path / "fleet.txt"
    fleet.write_text(
        "192.168.42.110\n"
        "192.168.42.118  # readonly - production line 3\n"
        "# just a comment line\n"
    )
    monkeypatch.setenv("WAGO_READONLY_HOSTS", "10.0.0.9")
    monkeypatch.setenv("WAGO_PLC_HOSTS_FILE", str(fleet))
    assert compute_readonly_hosts() == frozenset({"10.0.0.9", "192.168.42.118"})


def test_compute_readonly_hosts_missing_file_degrades_to_env(monkeypatch):
    monkeypatch.setenv("WAGO_READONLY_HOSTS", "10.0.0.9")
    monkeypatch.setenv("WAGO_PLC_HOSTS_FILE", "/nonexistent/fleet.txt")
    assert compute_readonly_hosts() == frozenset({"10.0.0.9"})
