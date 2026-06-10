FROM python:3.12-slim

WORKDIR /app

# curl is required for the docker-compose healthcheck
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# uv for fast, reproducible dependency resolution
RUN pip install --no-cache-dir uv

# Lockfile-aware copy (uv.lock* glob makes the lockfile optional)
COPY pyproject.toml uv.lock* ./

# Resolve + install deps system-wide (single-process container, no venv needed)
RUN uv lock && uv pip install --system --no-cache-dir -e . 

# Copy the full application package
COPY src/ ./src/

# EXPOSE documents the port; actual binding is controlled by docker-compose
EXPOSE 6042

CMD ["python", "src/main.py"]
