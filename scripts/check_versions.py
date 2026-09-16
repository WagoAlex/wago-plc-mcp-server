"""Fail when a published artifact's version drifts from version.txt.

PyPI, Docker, the MCP Registry entry and the .mcpb bundle must ship the same
version. build.sh stamps them all on a bump; this catches hand edits in CI.

    python3 scripts/check_versions.py
"""
import json
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def found_versions() -> dict[str, str]:
    server = json.loads((ROOT / "server.json").read_text())
    skill_md = (ROOT / "wago-plc-skill" / "SKILL.md").read_text()
    skill_version = re.search(r'^  version: "([^"]+)"', skill_md, re.MULTILINE)
    found = {
        "pyproject.toml": tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"],
        "integrations/mcpb/manifest.json": json.loads((ROOT / "integrations/mcpb/manifest.json").read_text())["version"],
        "server.json": server["version"],
        "wago-plc-skill/SKILL.md metadata.version": skill_version.group(1) if skill_version else "MISSING",
    }
    for pkg in server["packages"]:
        oci = pkg["registryType"] == "oci"
        found[f"server.json {pkg['registryType']} package"] = (
            pkg["identifier"].rsplit(":", 1)[-1] if oci else pkg["version"]
        )
    return found


def main() -> int:
    expected = (ROOT / "version.txt").read_text().strip()
    drift = {name: v for name, v in found_versions().items() if v != expected}
    for name, v in drift.items():
        print(f"version drift: {name} is {v}, version.txt is {expected}")
    if not drift:
        print(f"all version sources agree: {expected}")
    return 1 if drift else 0


if __name__ == "__main__":
    sys.exit(main())
