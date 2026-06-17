#!/usr/bin/env bash
# build.sh — local dev + CI release script for wago-plc-mcp-server
#
# Usage:
#   ./build.sh [--patch|--minor|--major] [--no-cache] [--start] [--push] [--release] [--ci]
#
#   --patch / --minor / --major  bump version in version.txt + pyproject.toml
#   --no-cache                   pass --no-cache to docker build
#   --start                      replace the running wmcp container after build
#   --push                       push image to Docker Hub
#   --release                    --push + git commit + tag (+ git push unless --ci)
#   --ci                         non-interactive; suppress git push (CI handles it)
#
# Examples:
#   ./build.sh --patch                  # bump, build, SBOM — no push
#   ./build.sh --patch --start          # bump, build, SBOM, restart container
#   ./build.sh --patch --no-cache       # bump, build without cache, SBOM
#   ./build.sh --release                # push current version + tag + git push
#   ./build.sh --patch --release        # bump + push + tag + git push
#   ./build.sh --patch --release --ci   # CI mode: bump + push + tag (CI pushes git)

set -euo pipefail

# ── defaults ─────────────────────────────────────────────────────────────────
BUMP=""
NO_CACHE=""
DO_START=false
DO_PUSH=false
DO_RELEASE=false
CI_MODE=false

# ── parse args ────────────────────────────────────────────────────────────────
for arg in "$@"; do
  case "$arg" in
    --patch)    BUMP=patch ;;
    --minor)    BUMP=minor ;;
    --major)    BUMP=major ;;
    --no-cache) NO_CACHE="--no-cache" ;;
    --start)    DO_START=true ;;
    --push)     DO_PUSH=true ;;
    --release)  DO_RELEASE=true; DO_PUSH=true ;;
    --ci)       CI_MODE=true ;;
    *)
      echo "error: unknown flag: $arg" >&2
      echo "usage: ./build.sh [--patch|--minor|--major] [--no-cache] [--start] [--push] [--release] [--ci]" >&2
      exit 1
      ;;
  esac
done

REPO="wagoalex/wago-plc-mcp-server"
VERSION=$(cat version.txt)

# ── version bump ──────────────────────────────────────────────────────────────
if [[ -n "$BUMP" ]]; then
  IFS='.' read -r V_MAJOR V_MINOR V_PATCH <<< "$VERSION"
  case "$BUMP" in
    patch) V_PATCH=$((V_PATCH + 1)) ;;
    minor) V_MINOR=$((V_MINOR + 1)); V_PATCH=0 ;;
    major) V_MAJOR=$((V_MAJOR + 1)); V_MINOR=0; V_PATCH=0 ;;
  esac
  VERSION="${V_MAJOR}.${V_MINOR}.${V_PATCH}"
  echo "$VERSION" > version.txt
  sed -i "s/^version = .*/version = \"${VERSION}\"/" pyproject.toml
  echo "▶ bumped to ${VERSION}"
fi

IMAGE="${REPO}:${VERSION}"
IMAGE_LATEST="${REPO}:latest"

# ── docker build ──────────────────────────────────────────────────────────────
echo "▶ building ${IMAGE}"
# shellcheck disable=SC2086
docker build ${NO_CACHE} -t "${IMAGE}" -t "${IMAGE_LATEST}" .

# ── SBOM (image-based, stronger than source-only) ────────────────────────────
SBOM_FILE="sbom-${VERSION}.json"
if command -v syft &>/dev/null; then
  echo "▶ generating SBOM → ${SBOM_FILE}"
  syft "${IMAGE}" -o cyclonedx-json="${SBOM_FILE}"
  mkdir -p sbom
  cp "${SBOM_FILE}" "sbom/sbom-${VERSION}.json"
  echo "  archived → sbom/sbom-${VERSION}.json"
else
  echo "⚠ syft not found — SBOM skipped"
  echo "  install: curl -sSfL https://raw.githubusercontent.com/anchore/syft/main/install.sh | sh -s -- -b /usr/local/bin"
  SBOM_FILE=""
fi

# ── docker push ───────────────────────────────────────────────────────────────
if $DO_PUSH; then
  echo "▶ pushing ${IMAGE}"
  docker push "${IMAGE}"
  docker push "${IMAGE_LATEST}"
  echo "  pushed ${IMAGE} + :latest"
fi

# ── git release (commit + tag) ────────────────────────────────────────────────
if $DO_RELEASE; then
  if [[ -n "$BUMP" ]]; then
    git add version.txt pyproject.toml
    git commit -m "chore: release v${VERSION}"
  fi

  if git rev-parse "v${VERSION}" &>/dev/null; then
    echo "⚠ tag v${VERSION} already exists — skipping tag"
  else
    git tag "v${VERSION}"
    echo "  tagged v${VERSION}"
  fi

  # Local mode: push immediately. CI mode: caller pushes (so it controls the token).
  if ! $CI_MODE; then
    git push origin HEAD --follow-tags
    echo "  pushed tag v${VERSION} to origin"
  fi
fi

# ── restart container ─────────────────────────────────────────────────────────
if $DO_START; then
  echo "▶ restarting wmcp"
  docker rm -f wmcp 2>/dev/null || true
  docker compose up -d
  docker ps --filter name=wmcp --format "  {{.Names}} {{.Status}}"
fi

echo "✓ done — ${IMAGE}"
if [[ -n "${SBOM_FILE}" ]]; then
  echo "  SBOM  → ${SBOM_FILE}"
fi
