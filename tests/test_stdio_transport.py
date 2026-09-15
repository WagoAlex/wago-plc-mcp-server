"""stdio transport contract - L0, no network, no PLC.

In stdio mode stdout IS the JSON-RPC channel (uvx, Claude Desktop, .mcpb).
Any banner or print on stdout corrupts the stream, and the server must start
inside the asyncio loop cli_main() already runs.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

_MAIN = Path(__file__).parent.parent / "src" / "main.py"

_INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "stdio-test", "version": "0"},
    },
}


def test_stdio_mode_answers_initialize_with_only_jsonrpc_on_stdout(tmp_path: Path) -> None:
    env = {
        **os.environ,
        "TRANSPORT": "stdio",
        "WAGO_PLC_HOSTS": "",
        "WAGO_PLC_HOSTS_FILE": "",
        "MCP_API_KEY": "",
        "AUDIT_LOG_FILE": str(tmp_path / "audit.log"),
        "LOG_LEVEL": "WARNING",
    }

    proc = subprocess.run(
        [sys.executable, str(_MAIN)],
        input=json.dumps(_INITIALIZE) + "\n",  # stdin closes after this -> server exits
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
        check=False,  # exit code is asserted via stdout content below
    )

    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    assert lines, f"no stdout; exit={proc.returncode}\nstderr:\n{proc.stderr[-2000:]}"
    for line in lines:
        json.loads(line)  # raises on any non-JSON-RPC output (banners, prints)
    assert json.loads(lines[0])["id"] == 1
    assert "result" in json.loads(lines[0])
