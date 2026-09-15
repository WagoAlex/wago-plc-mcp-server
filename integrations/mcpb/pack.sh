#!/usr/bin/env bash
# Build the Claude Desktop extension (.mcpb) from the tracked sources.
#
#   integrations/mcpb/pack.sh            -> integrations/mcpb/wago-plc-mcp-server-<version>.mcpb
#
# The bundle ships source + pyproject.toml + uv.lock (server.type "uv"): Claude Desktop
# installs Python and dependencies itself, so the bundle never lags behind PyPI.
# Runs the mcpb CLI in a node container, like every other tool in this repo.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
VERSION="$(cat "$ROOT/version.txt")"
MCPB_CLI="@anthropic-ai/mcpb@2.1.2"
OUT="wago-plc-mcp-server-${VERSION}.mcpb"

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

cp "$HERE/manifest.json" "$HERE/icon.png" "$STAGE/"
cp "$ROOT/pyproject.toml" "$ROOT/uv.lock" "$ROOT/README.md" "$ROOT/LICENSE" "$STAGE/"
mkdir "$STAGE/src"
cp "$ROOT"/src/*.py "$STAGE/src/"

# Version comes from version.txt, same source as Docker and PyPI.
sed -i "s/\"version\": \"[^\"]*\"/\"version\": \"${VERSION}\"/" "$STAGE/manifest.json"

docker run --rm -u "$(id -u):$(id -g)" \
  -e npm_config_cache=/tmp/npm -e npm_config_update_notifier=false \
  -v "$STAGE:/bundle" -v "$HERE:/out" -w /bundle node:22-slim \
  sh -c "npx -y $MCPB_CLI validate manifest.json && npx -y $MCPB_CLI pack /bundle /out/$OUT"

echo "built integrations/mcpb/$OUT"
