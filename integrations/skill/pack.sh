#!/usr/bin/env bash
# Build the distributable .skill bundle for claude.ai / Skills API / Agent SDK
# upload.
#
#   integrations/skill/pack.sh   -> integrations/skill/wago-plc-skill-<version>.skill
#
# A .skill file is just a zip of the skill folder (see anthropics/skills'
# package_skill.py) - no build step or extra tooling needed, but the
# frontmatter is validated first so a broken skill never ships as a release
# asset. Validation rules mirror the Agent Skills standard: only the six
# portable frontmatter fields, description <=1024 chars, compatibility
# <=500 chars, name is kebab-case.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
VERSION="$(cat "$ROOT/version.txt")"
SKILL_DIR="wago-plc-skill"
OUT="wago-plc-skill-${VERSION}.skill"

cd "$ROOT"

python3 -c "import yaml" 2>/dev/null || pip install --quiet pyyaml

python3 - "$SKILL_DIR" <<'PY'
import re, sys, yaml

skill_dir = sys.argv[1]
content = open(f"{skill_dir}/SKILL.md").read()
match = re.match(r"^---\n(.*?)\n---\n", content, re.DOTALL)
if not match:
    sys.exit(f"error: {skill_dir}/SKILL.md has no YAML frontmatter")
fm = yaml.safe_load(match.group(1))

allowed = {"name", "description", "license", "allowed-tools", "metadata", "compatibility"}
extra = set(fm) - allowed
if extra:
    sys.exit(f"error: frontmatter keys not in the Agent Skills standard: {sorted(extra)}")
if "name" not in fm or "description" not in fm:
    sys.exit("error: frontmatter must have 'name' and 'description'")
if not re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", fm["name"]):
    sys.exit(f"error: name {fm['name']!r} must be kebab-case")
if len(fm["description"]) > 1024:
    sys.exit(f"error: description is {len(fm['description'])} chars, max 1024")
if len(fm.get("compatibility", "")) > 500:
    sys.exit(f"error: compatibility is {len(fm['compatibility'])} chars, max 500")

print("frontmatter OK for cross-product packaging")
PY

rm -f "integrations/skill/${OUT}"
zip -r -X -q "integrations/skill/${OUT}" "$SKILL_DIR" \
  -x '*/__pycache__/*' -x '*.pyc' -x '*/.DS_Store'

echo "built integrations/skill/${OUT}"
