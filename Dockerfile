FROM python:3.14-slim AS base

WORKDIR /app

# curl is required for the docker-compose healthcheck
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

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

# Copy test suite into the image
COPY tests/ ./tests/
