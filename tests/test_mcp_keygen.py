"""Unit test for mcp_keygen.py's argument guard - no I/O beyond the key path write."""
import sys
import pytest
import mcp_keygen


def test_unexpected_args_refuse_to_run(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["mcp_keygen.py", "--help"])
    with pytest.raises(SystemExit) as exc:
        mcp_keygen.main()
    assert exc.value.code == 1


def test_bare_invocation_regenerates(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["mcp_keygen.py"])
    monkeypatch.setattr(mcp_keygen, "_KEY_PATH", tmp_path / "mcp_api_key")

    mcp_keygen.main()

    assert (tmp_path / "mcp_api_key").exists()
    assert "MCP API KEY REGENERATED" in capsys.readouterr().out
