"""Unit tests for the SECURITY_PROFILE=hardened fail-closed TLS gate
(src/config.py::check_security_profile). Plan: .claude/plans/iec62443-4-2-hardening.plan.md, Phase 1.
"""
import pytest

from config import check_security_profile


def test_default_profile_unaffected_even_with_no_tls(monkeypatch):
    monkeypatch.delenv("SECURITY_PROFILE", raising=False)
    monkeypatch.delenv("WAGO_TLS_CA", raising=False)
    monkeypatch.delenv("MCP_TLS_CERT", raising=False)
    monkeypatch.delenv("MCP_TLS_KEY", raising=False)
    check_security_profile()  # must not raise


def test_hardened_with_no_tls_at_all_raises(monkeypatch):
    monkeypatch.setenv("SECURITY_PROFILE", "hardened")
    monkeypatch.delenv("WAGO_TLS_CA", raising=False)
    monkeypatch.delenv("MCP_TLS_CERT", raising=False)
    monkeypatch.delenv("MCP_TLS_KEY", raising=False)
    with pytest.raises(SystemExit) as exc:
        check_security_profile()
    assert exc.value.code == 1


@pytest.mark.parametrize("bad_ca", ["", "false", "FALSE", "0"])
def test_hardened_with_wda_tls_disabled_raises(monkeypatch, bad_ca):
    monkeypatch.setenv("SECURITY_PROFILE", "hardened")
    monkeypatch.setenv("WAGO_TLS_CA", bad_ca)
    monkeypatch.setenv("MCP_TLS_CERT", "/certs/mcp.crt")
    monkeypatch.setenv("MCP_TLS_KEY", "/certs/mcp.key")
    with pytest.raises(SystemExit):
        check_security_profile()


def test_hardened_with_mcp_tls_missing_raises(monkeypatch):
    monkeypatch.setenv("SECURITY_PROFILE", "hardened")
    monkeypatch.setenv("WAGO_TLS_CA", "/certs/wda-ca.pem")
    monkeypatch.delenv("MCP_TLS_CERT", raising=False)
    monkeypatch.delenv("MCP_TLS_KEY", raising=False)
    with pytest.raises(SystemExit):
        check_security_profile()


def test_hardened_with_both_legs_configured_starts_normally(monkeypatch):
    monkeypatch.setenv("SECURITY_PROFILE", "hardened")
    monkeypatch.setenv("WAGO_TLS_CA", "/certs/wda-ca.pem")
    monkeypatch.setenv("MCP_TLS_CERT", "/certs/mcp.crt")
    monkeypatch.setenv("MCP_TLS_KEY", "/certs/mcp.key")
    check_security_profile()  # must not raise


def test_hardened_with_wda_tls_true_and_mcp_tls_configured_starts_normally(monkeypatch):
    monkeypatch.setenv("SECURITY_PROFILE", "hardened")
    monkeypatch.setenv("WAGO_TLS_CA", "true")  # system trust store, per resolve_tls_verify
    monkeypatch.setenv("MCP_TLS_CERT", "/certs/mcp.crt")
    monkeypatch.setenv("MCP_TLS_KEY", "/certs/mcp.key")
    check_security_profile()  # must not raise


def test_profile_value_is_case_insensitive(monkeypatch):
    monkeypatch.setenv("SECURITY_PROFILE", "HARDENED")
    monkeypatch.delenv("WAGO_TLS_CA", raising=False)
    monkeypatch.delenv("MCP_TLS_CERT", raising=False)
    monkeypatch.delenv("MCP_TLS_KEY", raising=False)
    with pytest.raises(SystemExit):
        check_security_profile()
