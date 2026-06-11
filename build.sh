#!/bin/bash

# --- Configuration ---
VERSION_FILE="version.txt"
IMAGE_NAME="wagoalex/wago-plc-mcp-server"
SCRIPT_NAME=$(basename "$0")

# --- Load Environment Variables from .env File ---
ENV_FILE=".env"
if [ -f "$ENV_FILE" ]; then
    echo "Loading environment variables from $ENV_FILE..."
    set -a
    source "$ENV_FILE"
    set +a
else
    echo "No $ENV_FILE file found in the current directory. Relying on existing environment variables."
fi

# --- Initialization ---
set -e

# --- Usage / Help Function ---
print_usage() {
  cat << EOF
Usage: ${SCRIPT_NAME} [options]

Builds the WAGO PLC MCP server Docker image and optionally starts the server.
Version (${VERSION_FILE}) must be in Major.Minor.Patch format (e.g., 1.2.3).

Options:
  --major          Increment the major version (resets minor and patch to 0).
  --minor          Increment the minor version (resets patch to 0).
  --patch          Increment the patch version (default).
  --release        Use the current version without incrementing.
                   Triggers push to Docker Hub.
  --no-cache       Use --no-cache for 'docker compose build'.
  --start          Start the server after building using 'docker compose up -d'.
  --help           Display this help message and exit.

Default: Increments patch version and builds the image.
EOF
}

# --- Argument Parsing ---
for arg in "$@"; do
  if [ "$arg" == "--help" ]; then
    print_usage
    exit 0
  fi
done

INCREMENT_TYPE="patch"
PUSH_DOCKER_FLAG=false
USE_NO_CACHE=false
START_SERVER=false

while [[ "$#" -gt 0 ]]; do
    case $1 in
        --major) INCREMENT_TYPE="major"; shift ;;
        --minor) INCREMENT_TYPE="minor"; shift ;;
        --patch) INCREMENT_TYPE="patch"; shift ;;
        --release)
            INCREMENT_TYPE="none"
            PUSH_DOCKER_FLAG=true
            shift ;;
        --no-cache) USE_NO_CACHE=true; shift ;;
        --start) START_SERVER=true; shift ;;
        *) echo "Error: Unknown parameter passed: $1"; echo ""; print_usage; exit 1 ;;
    esac
done

# --- Version Handling ---
if [ ! -f "$VERSION_FILE" ]; then
    echo "Version file ($VERSION_FILE) not found. Creating with initial version 0.1.0."
    echo "0.1.0" > "$VERSION_FILE"
fi

CURRENT_VERSION=$(cat "$VERSION_FILE")

VERSION_REGEX="^[0-9]+\.[0-9]+\.[0-9]+$"
if ! [[ "$CURRENT_VERSION" =~ $VERSION_REGEX ]]; then
    echo "Error: Version '$CURRENT_VERSION' in '$VERSION_FILE' does not match required Major.Minor.Patch format (e.g., 1.2.3)."
    exit 1
fi
echo "Current version read from $VERSION_FILE: $CURRENT_VERSION (Format: OK)"

increment_version() {
    local version=$1
    local part=$2
    local major minor patch

    IFS='.' read -r major minor patch <<< "$version"

    case $part in
        major)
            major=$((major + 1))
            minor=0
            patch=0
            ;;
        minor)
            minor=$((minor + 1))
            patch=0
            ;;
        patch)
            patch=$((patch + 1))
            ;;
        *)
            echo "Error: Invalid increment part '$part' provided to increment_version function."
            exit 1
            ;;
    esac

    echo "$major.$minor.$patch"
}

if [ "$INCREMENT_TYPE" == "none" ]; then
    NEW_VERSION=$CURRENT_VERSION
    echo "Using current version (specified by --release): $NEW_VERSION"
else
    NEW_VERSION=$(increment_version "$CURRENT_VERSION" "$INCREMENT_TYPE")
    echo "Incrementing version ($INCREMENT_TYPE): $CURRENT_VERSION -> $NEW_VERSION"
    echo "$NEW_VERSION" > "$VERSION_FILE"
    echo "Updated $VERSION_FILE to $NEW_VERSION"
fi

# --- Build Using Docker Compose ---
echo "Building WAGO PLC MCP server using Docker Compose (${IMAGE_NAME}:${NEW_VERSION})..."
BUILD_ARGS=""
if [ "$USE_NO_CACHE" = true ]; then
    echo "Using --no-cache for Docker Compose build."
    BUILD_ARGS="--no-cache"
fi

docker compose build ${BUILD_ARGS} wago-plc-mcp-server
docker tag "${IMAGE_NAME}:latest" "${IMAGE_NAME}:${NEW_VERSION}"

# --- SBOM (T5) ---
SBOM_FILE="sbom-${NEW_VERSION}.json"
echo "Generating SBOM for ${IMAGE_NAME}:${NEW_VERSION}..."
syft "${IMAGE_NAME}:${NEW_VERSION}" -o cyclonedx-json --file "${SBOM_FILE}"
echo "SBOM written to ${SBOM_FILE}"

# --- Start the Server (Optional) ---
if [ "$START_SERVER" = true ]; then
    echo "Starting the server using 'docker compose up'..."
    docker compose up
fi

# --- Docker Push (Conditional) ---
if [ "$PUSH_DOCKER_FLAG" = true ]; then
    echo "Pushing Docker images to Docker Hub (triggered by --release)..."
    echo "Pushing ${IMAGE_NAME}:${NEW_VERSION}..."
    docker push "${IMAGE_NAME}:${NEW_VERSION}"
    echo "Pushing ${IMAGE_NAME}:latest..."
    docker push "${IMAGE_NAME}:latest"
    echo "Docker images pushed."
    mkdir -p sbom
    cp "${SBOM_FILE}" "sbom/${SBOM_FILE}"
    echo "SBOM archived to sbom/${SBOM_FILE}"
else
    echo "Skipping Docker Hub push (specify --release flag to push this version)."
fi

echo "--------------------------------------------------"
echo "Build process completed for version $NEW_VERSION."
if [ "$START_SERVER" = true ]; then
    echo "Server started in detached mode."
fi
echo "--------------------------------------------------"

exit 0