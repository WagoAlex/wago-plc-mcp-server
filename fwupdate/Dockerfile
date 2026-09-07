FROM python:3.12-slim AS base

# git is a runtime dependency, not a build convenience: authz.py shells out to
# it to prove the firmware policy is committed and unmodified.
RUN apt-get update && apt-get install -y --no-install-recommends git \
 && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir httpx==0.27.* pyyaml==6.* boto3==1.35.*

WORKDIR /app
# audit.py comes from src/: the tamper-evident chain has ONE implementation,
# shared with the MCP server and scripts/apply.py. Never fork it.
COPY src/audit.py .
COPY fwupdate/fw_update.py fwupdate/catalog.py fwupdate/build_catalog.py \
     fwupdate/source.py fwupdate/authz.py fwupdate/fleet.py .

# The policy file is mounted from a git checkout, so mark it safe to inspect
# regardless of the uid mismatch between host and container.
RUN git config --global --add safe.directory '*'

ENTRYPOINT ["python", "fw_update.py"]

FROM base AS dev
RUN pip install --no-cache-dir pytest==8.*
COPY fwupdate/test_catalog.py fwupdate/test_poll.py fwupdate/test_source.py \
     fwupdate/test_authz.py fwupdate/test_audit_chain.py .
ENTRYPOINT []
