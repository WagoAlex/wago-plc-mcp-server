"""Post-release check: every public channel serves the released version.

    python3 scripts/verify_release.py 2.3.1

Checks PyPI, Docker Hub, the MCP Registry, the .mcpb asset on the GitHub Release,
and that `uvx wago-plc-mcp-server==<version>` from PyPI answers initialize with
that version. Public HTTP APIs only (plus uvx), so it runs anywhere without gh
or a Docker daemon. Exits 1 on any miss, so drift shows up red on release day.
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

PACKAGE = "wago-plc-mcp-server"
IMAGE = "wagoalex/wago-plc-mcp-server"
REGISTRY_NAME = "io.github.WagoAlex/wago-plc-mcp-server"
GITHUB_REPO = os.environ.get("GITHUB_REPOSITORY", "WagoAlex/wago-plc-mcp-server")

# PyPI's CDN and the registry index can lag a few minutes behind a publish.
# ponytail: fixed retry budget, raise ATTEMPTS if releases keep flaking.
ATTEMPTS = 6
WAIT_SECONDS = 30


def fetch_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": "wago-plc-mcp-server-release-verify"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def check_pypi(version: str) -> None:
    fetch_json(f"https://pypi.org/pypi/{PACKAGE}/{version}/json")


def check_docker_hub(version: str) -> None:
    fetch_json(f"https://hub.docker.com/v2/repositories/{IMAGE}/tags/{version}")


def check_registry(version: str) -> None:
    servers = fetch_json(f"https://registry.modelcontextprotocol.io/v0/servers?search={REGISTRY_NAME}")["servers"]
    for entry in servers:
        server = entry.get("server", entry)
        official = entry.get("_meta", {}).get("io.modelcontextprotocol.registry/official", {})
        if server.get("name") == REGISTRY_NAME and server.get("version") == version:
            if not official.get("isLatest"):
                raise AssertionError(f"{version} is listed but not marked latest")
            return
    raise AssertionError(f"{REGISTRY_NAME} {version} not listed")


def check_release_asset(version: str) -> None:
    release = fetch_json(f"https://api.github.com/repos/{GITHUB_REPO}/releases/tags/v{version}")
    names = {asset["name"] for asset in release["assets"]}
    for wanted in (f"{PACKAGE}-{version}.mcpb", f"wago-plc-skill-{version}.skill"):
        if wanted not in names:
            raise AssertionError(f"{wanted} missing, assets: {sorted(names)}")


def check_uvx_initialize(version: str) -> None:
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "verify", "version": "0"}},
    }
    env = {**os.environ, "TRANSPORT": "stdio", "WAGO_PLC_HOSTS": "", "AUDIT_LOG_FILE": "/tmp/verify-audit.log", "LOG_LEVEL": "WARNING"}
    proc = subprocess.run(
        ["uvx", "--refresh", f"{PACKAGE}=={version}"],
        input=json.dumps(request) + "\n",
        capture_output=True,
        text=True,
        env=env,
        timeout=300,
        check=False,
    )
    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    if not lines:
        raise AssertionError(f"no stdout (exit {proc.returncode}): {proc.stderr[-500:]}")
    reported = json.loads(lines[0])["result"]["serverInfo"]["version"]
    if reported != version:
        raise AssertionError(f"initialize reported {reported!r}")


CHECKS = [
    ("PyPI", check_pypi),
    ("Docker Hub", check_docker_hub),
    ("MCP Registry", check_registry),
    ("GitHub Release assets (.mcpb + .skill)", check_release_asset),
    ("uvx from PyPI", check_uvx_initialize),
]


def run_check(name: str, check, version: str) -> str | None:
    """Return None on success, else the last error after all attempts."""
    error = None
    for attempt in range(1, ATTEMPTS + 1):
        try:
            check(version)
            return None
        except Exception as exc:  # noqa: BLE001 - any failure is a miss worth retrying
            error = f"{type(exc).__name__}: {exc}"
            if attempt < ATTEMPTS:
                time.sleep(WAIT_SECONDS)
    return error


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    version = sys.argv[1]
    failures = 0
    for name, check in CHECKS:
        error = run_check(name, check, version)
        if error:
            failures += 1
            print(f"FAIL {name}: {error}")
        else:
            print(f"ok   {name}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
