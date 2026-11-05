# curl from source: Debian trixie has 8.14.1 and backports has 8.21.0, both with open
# CVEs on curl.se. Only the healthcheck uses curl, so this build keeps it self-contained.
# ponytail: pinned by hand, CI does not scan the image. Update both values for a new
# curl release, after you check the .asc signature (key 27EDEAF22F3ABCEB50DB9A125CC908FDB71E12C2).
FROM python:3.14-slim AS curl-build
ARG CURL_VERSION=8.23.0
ARG CURL_SHA256=e3de77cfa6367083c776a26647fc9f633b538c06c3baa73d931a252ac8f72b49
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc make libc6-dev libssl-dev \
    && python -c "import urllib.request as u; u.urlretrieve('https://curl.se/download/curl-${CURL_VERSION}.tar.gz', '/tmp/curl.tar.gz')" \
    && echo "${CURL_SHA256}  /tmp/curl.tar.gz" | sha256sum -c - \
    && tar -xzf /tmp/curl.tar.gz -C /tmp \
    && cd "/tmp/curl-${CURL_VERSION}" \
    && ./configure --with-openssl --disable-shared --disable-ldap --disable-manual \
        --without-libpsl --without-nghttp2 --without-libidn2 --without-brotli --without-zstd \
    && make -j"$(nproc)" \
    && make install \
    && strip /usr/local/bin/curl

FROM python:3.14-slim AS base

# MCP Registry ownership marker for the OCI package; must equal server.json "name"
LABEL io.modelcontextprotocol.server.name="io.github.WagoAlex/wago-plc-mcp-server"

WORKDIR /app

# curl is required for the docker-compose healthcheck
COPY --from=curl-build /usr/local/bin/curl /usr/local/bin/curl

# uv for fast, reproducible dependency resolution
RUN pip install --no-cache-dir uv

# Lockfile-aware copy (uv.lock* glob makes the lockfile optional)
COPY pyproject.toml uv.lock* ./

# Resolve + install production deps system-wide (single-process container, no venv needed)
# src/ must exist for setuptools editable install; COPY src/ below fills in the real files
RUN mkdir -p src && uv lock && uv pip install --system --no-cache-dir -e .

# Copy the full application package
COPY src/ ./src/

# EXPOSE documents the port; actual binding is controlled by docker-compose
EXPOSE 6042

CMD ["python", "src/main.py"]

# ── dev target — extends base with test tooling; never used in production ──
FROM base AS dev

# Install dev dependency group (pytest, respx, pytest-asyncio, pytest-cov, pyyaml, …)
RUN uv pip install --system --no-cache-dir --group dev

# Reconciler script and FW31 cassettes (contract tests). The test suite itself is
# local only and not in the repository, so it is mounted at run time:
#   docker run --rm -v "$PWD/tests:/app/tests:ro" wmcp-dev pytest tests/ -m "not live and not mutate and not soak"
COPY scripts/ ./scripts/
COPY docs/*-fw31-parameters-raw.json ./docs/
