"""Environment / fleet / secret configuration parsing.

Extracted from main.py: everything that turns env vars, the fleet file, and
Docker Secrets into runtime configuration. No side effects at import time.
"""
import os
import re
from pathlib import Path

from loguru import logger


def read_secret(name: str) -> str | None:
    """Read a Docker Secret from /run/secrets/. Returns None if absent or empty."""
    try:
        return Path(f"/run/secrets/{name}").read_text().strip() or None
    except OSError:
        return None


def resolve_tls_verify() -> bool | str:
    """Resolve WDA TLS verification from WAGO_TLS_CA env var.

    Not set / 'false' / '0' → False  (verification disabled — warns at startup)
    'true' / '1'            → True   (system trust store)
    Any other value         → path to CA bundle (PEM file or directory)
    Per-PLC override: Docker Secret plc_cert_<ip_underscored> (resolved in PLCManager.register)
    """
    val = os.getenv("WAGO_TLS_CA", "").strip()
    if not val or val.lower() in {"false", "0"}:
        logger.warning(
            "[tls] WDA TLS verification DISABLED — connections to PLCs are not verified. "
            "Set WAGO_TLS_CA=true (system CA) or WAGO_TLS_CA=/path/to/ca.pem to enable."
        )
        return False
    if val.lower() in {"true", "1"}:
        logger.info("[tls] WDA TLS verification enabled (system trust store)")
        return True
    logger.info(f"[tls] WDA TLS verification enabled (CA bundle: {val})")
    return val


def _load_per_plc_secrets() -> dict[str, str]:
    """Scan /run/secrets/ for plc_password_<ip> files and return {ip: password}.

    Secret name 'plc_password_10_0_0_1' maps to IP '10.0.0.1'.
    """
    secrets_dir = Path("/run/secrets")
    result: dict[str, str] = {}
    if not secrets_dir.is_dir():
        return result
    for f in secrets_dir.iterdir():
        if f.name.startswith("plc_password_"):
            ip = f.name.removeprefix("plc_password_").replace("_", ".")
            pwd = f.read_text().strip()
            if pwd:
                result[ip] = pwd
    return result


def parse_plcs_from_env() -> list[tuple[str, str, str]]:
    """Parse PLC list from environment + Docker Secrets, supporting three formats.

    Password resolution order (highest priority first):
      1. Docker Secret  /run/secrets/plc_password_<ip-with-underscores>  (per-PLC)
      2. Env var        PLC_PASSWORDS_<ip-with-underscores>               (per-PLC, backward-compat)
      3. Docker Secret  /run/secrets/plc_default_password                 (shared default)
      4. Env var        DEFAULT_PLC_PASSWORD                              (shared default, dev fallback)
      5. Hardcoded      "wago"

    Host formats (all three can be combined; IPs are merged):
      WAGO_PLC_HOSTS=10.0.0.1,10.0.0.2        (CSV, suitable for small fleets)
      WAGO_PLC_HOSTS_FILE=/app/data/fleet.txt  (one IP per line, # comments; large fleets)
      PLC_PASSWORDS_10_0_0_1=secret_a          (per-PLC env, also extends host list)
    Per-PLC credentials override the shared default for matching IPs.
    """
    user = os.getenv("DEFAULT_PLC_USERNAME", "admin")
    default_pwd = (
        read_secret("plc_default_password")
        or os.getenv("DEFAULT_PLC_PASSWORD", "wago")
    )
    if default_pwd in {"wago", "admin", "password", "123456", ""}:
        logger.warning(
            "[config] DEFAULT_PLC_PASSWORD is a known factory default — "
            "set a strong password via Docker Secret (plc_default_password) or env var"
        )
    per_plc_secrets = _load_per_plc_secrets()
    plcs: dict[str, tuple[str, str]] = {}

    hosts_csv = os.getenv("WAGO_PLC_HOSTS", "").strip()
    if hosts_csv:
        for ip in (h.strip() for h in hosts_csv.split(",")):
            if ip:
                plcs[ip] = (user, per_plc_secrets.get(ip, default_pwd))

    hosts_file = os.getenv("WAGO_PLC_HOSTS_FILE", "").strip()
    if hosts_file:
        p = Path(hosts_file)
        if p.exists():
            for line in p.read_text().splitlines():
                ip = line.split("#")[0].strip()
                if ip:
                    plcs[ip] = (user, per_plc_secrets.get(ip, default_pwd))
        else:
            logger.warning(f"[config] WAGO_PLC_HOSTS_FILE={hosts_file} not found — skipping")

    for key, val in os.environ.items():
        m = re.match(r"^PLC_PASSWORDS_(\d+_\d+_\d+_\d+)$", key)
        if m:
            ip = m.group(1).replace("_", ".")
            plcs[ip] = (user, per_plc_secrets.get(ip) or val or default_pwd)

    return [(ip, u, p) for ip, (u, p) in plcs.items()]
