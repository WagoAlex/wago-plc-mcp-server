"""Environment / fleet / secret configuration parsing.

Extracted from main.py: everything that turns env vars, the fleet file, and
Docker Secrets into runtime configuration. No side effects at import time.
"""
import os
import re
import sys
from pathlib import Path

from loguru import logger


def read_secret(name: str) -> str | None:
    """Read a Docker Secret from /run/secrets/. Returns None if absent or empty."""
    try:
        return Path(f"/run/secrets/{name}").read_text().strip() or None
    except OSError:
        return None


def resolve_user_path(path: str | None) -> str | None:
    """Expand `~` and a literal `${HOME}` in a log path from the environment.

    A .mcpb install keeps the `${HOME}` of a saved form value: mcpb does not expand
    placeholders inside user_config values. loguru would read `{HOME}` as a format
    field and raise KeyError. expanduser uses USERPROFILE on Windows.
    """
    return os.path.expanduser(path.replace("${HOME}", "~")) if path else path


def check_security_profile() -> None:
    """Fail closed at startup when SECURITY_PROFILE=hardened but TLS isn't
    fully configured on both legs (server<->PLC and client<->server).

    Mirrors auth._check_key_entropy's fail-loud pattern: log the specific
    gap, then SystemExit(1) rather than starting in a state that contradicts
    the requested profile. Default profile (unset) is untouched - today's
    warn-and-continue TLS behavior stays the default so existing deployments
    don't break on upgrade. This is Phase 1 of
    .claude/plans/iec62443-4-2-hardening.plan.md (FR4, transport
    confidentiality) - it only gates whether TLS is *configured*, not
    whether it's trustworthy; a bad cert still starts today, hardened or not.
    """
    if os.getenv("SECURITY_PROFILE", "").strip().lower() != "hardened":
        return

    wda_ca = os.getenv("WAGO_TLS_CA", "").strip()
    wda_tls_ok = bool(wda_ca) and wda_ca.lower() not in {"false", "0"}

    # stdio (Claude Desktop extension, uvx) has no client<->server network leg -
    # the client talks to the server over a local pipe - so only the WDA leg
    # needs TLS there.
    stdio = os.getenv("TRANSPORT", "").strip().lower() == "stdio"
    mcp_tls_ok = stdio or (
        bool(os.getenv("MCP_TLS_CERT", "").strip()) and bool(os.getenv("MCP_TLS_KEY", "").strip())
    )

    if wda_tls_ok and mcp_tls_ok:
        return

    missing = []
    if not wda_tls_ok:
        missing.append("WAGO_TLS_CA (must be a real CA/cert path, not unset/false/0)")
    if not mcp_tls_ok:
        missing.append("MCP_TLS_CERT + MCP_TLS_KEY")
    logger.error(
        f"[security] SECURITY_PROFILE=hardened requires TLS on both legs; "
        f"missing: {', '.join(missing)}. Refusing to start hardened over plaintext transport."
    )
    raise SystemExit(1)


def resolve_tls_verify() -> bool | str:
    """Resolve WDA TLS verification from WAGO_TLS_CA env var.

    Not set / 'false' / '0' → False  (verification disabled - warns at startup)
    'true' / '1'            → True   (system trust store)
    Any other value         → path to CA bundle (PEM file or directory)
    Per-PLC override: Docker Secret plc_cert_<ip_underscored> (resolved in PLCManager.register)
    """
    val = os.getenv("WAGO_TLS_CA", "").strip()
    if not val or val.lower() in {"false", "0"}:
        logger.warning(
            "[tls] WDA TLS verification DISABLED - connections to PLCs are not verified. "
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


def _password_pairs(entries: list[str], source: str, unit: str) -> dict[str, str]:
    """Parse 'ip=pwd' entries into {ip: password}. Log the position of a problem, never its text."""
    result: dict[str, str] = {}
    for number, entry in enumerate(entries, 1):
        ip, sep, pwd = (part.strip() for part in entry.partition("="))
        if sep and ip and pwd:
            result[ip] = pwd
            if " #" in pwd:
                logger.warning(
                    f"[config] {source} {unit} {number}: the password contains ' #' and the server uses "
                    "the full text. Write a comment on its own line."
                )
        elif entry.strip():
            logger.warning(f"[config] {source} {unit} {number}: not ip=password - skipping")
    return result


def _parse_password_field(blob: str) -> dict[str, str]:
    """PLC_PASSWORDS: comma-separated pairs, so a password cannot contain a comma."""
    return _password_pairs(blob.split(","), "PLC_PASSWORDS", "entry")


def _parse_password_file(text: str) -> dict[str, str]:
    """PLC_PASSWORDS_FILE: one pair per line. A comment has its own line, so a password can hold any character."""
    lines = ["" if line.lstrip().startswith("#") else line for line in text.splitlines()]
    return _password_pairs(lines, "PLC_PASSWORDS_FILE", "line")


# Problems of the last parse_plcs_from_env() run. The server shows them in its tool replies.
CONFIG_PROBLEMS: list[str] = []


def log_location_hint(platform: str | None = None, transport: str | None = None) -> str:
    """Tell the user where to find the server log. The answer depends on the OS and on the transport.

    The Claude Desktop screen is the documented way. The folders are the known places of the
    log files. For an extension (.mcpb) Anthropic does not document the file names.
    """
    platform = platform or sys.platform
    transport = transport or os.getenv("TRANSPORT", "streamable-http").strip().lower()
    log_file = resolve_user_path(os.getenv("LOG_FILE"))
    if transport != "stdio":
        hint = "Server log: run 'docker logs wmcp' on the Docker host."
        return f"{hint} Debug log file: {log_file}." if log_file else hint
    if platform == "win32":
        folders = (
            r"%APPDATA%\Claude\logs. Microsoft Store install: "
            r"%LOCALAPPDATA%\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude\logs"
        )
    elif platform == "darwin":
        folders = "~/Library/Logs/Claude"
    else:
        folders = "~/.config/Claude/logs"
    hint = (
        "Server log: open Claude Desktop, then Settings > Desktop app > Extensions > Manage > Local MCP servers. "
        f"Log files on disk: {folders}. The file name can differ, so look for 'mcp' in the name."
    )
    if log_file:
        return f"{hint} Debug log file of the server: {log_file}."
    return f"{hint} Tip: set 'Logs: debug log file' in the extension form to get a log file from the server itself."


def _read_optional(path: str, name: str) -> str | None:
    """Read a config file. A missing or unreadable file (for example on a network share) is skipped, never fatal."""
    try:
        return Path(path).read_text()
    except FileNotFoundError:
        problem = f"{name}={path} not found"
        logger.warning(f"[config] {problem} - skipping")
    except OSError as e:
        problem = f"{name}={path} cannot be read ({e}). Keep this file on a local disk, not on a network share"
        logger.error(f"[config] {problem} - skipping")
    CONFIG_PROBLEMS.append(problem)
    return None


def parse_plcs_from_env() -> list[tuple[str, str, str]]:
    """Parse PLC list from environment + Docker Secrets, supporting three formats.

    Password resolution order (highest priority first):
      1. Docker Secret  /run/secrets/plc_password_<ip-with-underscores>  (per-PLC)
      2. Env var        PLC_PASSWORDS_FILE=/path/to/file                 (per-PLC, file - many PLCs)
      2. Env var        PLC_PASSWORDS_<ip-with-underscores>               (per-PLC, backward-compat)
      2. Env var        PLC_PASSWORDS=<ip>=<pwd>,<ip>=<pwd>,...           (per-PLC, one field - a few PLCs)
      3. Docker Secret  /run/secrets/plc_default_password                 (shared default)
      4. Env var        DEFAULT_PLC_PASSWORD                              (shared default, dev fallback)
      5. Hardcoded      "wago"

    Host formats (all can be combined; IPs are merged):
      WAGO_PLC_HOSTS=10.0.0.1,10.0.0.2         (CSV, suitable for small fleets)
      WAGO_PLC_HOSTS_FILE=/app/data/fleet.txt  (one IP per line, # comments; large fleets)
      PLC_PASSWORDS_10_0_0_1=secret_a          (per-PLC env, also extends host list)
      PLC_PASSWORDS=10.0.0.2=secret_b,10.0.0.3=secret_c        (bulk per-PLC env, also extends host list)
      PLC_PASSWORDS_FILE=/app/data/passwords.txt                (bulk per-PLC file, also extends host list)
    Per-PLC credentials override the shared default for matching IPs.
    """
    CONFIG_PROBLEMS.clear()
    user = os.getenv("DEFAULT_PLC_USERNAME", "admin")
    default_pwd = (
        read_secret("plc_default_password")
        or os.getenv("DEFAULT_PLC_PASSWORD", "wago")
    )
    if default_pwd in {"wago", "admin", "password", "123456", ""}:
        logger.warning(
            "[config] DEFAULT_PLC_PASSWORD is a known factory default - "
            "set a strong password via Docker Secret (plc_default_password) or env var"
        )
    password_overrides = _parse_password_field(os.getenv("PLC_PASSWORDS", ""))
    overrides_file = os.getenv("PLC_PASSWORDS_FILE", "").strip()
    if overrides_file:
        text = _read_optional(overrides_file, "PLC_PASSWORDS_FILE")
        if text is not None:
            password_overrides = {**password_overrides, **_parse_password_file(text)}
    per_plc_secrets = {**password_overrides, **_load_per_plc_secrets()}
    plcs: dict[str, tuple[str, str]] = {}

    hosts_csv = os.getenv("WAGO_PLC_HOSTS", "").strip()
    if hosts_csv:
        for ip in (h.strip() for h in hosts_csv.split(",")):
            if ip:
                plcs[ip] = (user, per_plc_secrets.get(ip, default_pwd))

    hosts_file = os.getenv("WAGO_PLC_HOSTS_FILE", "").strip()
    if hosts_file:
        text = _read_optional(hosts_file, "WAGO_PLC_HOSTS_FILE")
        for line in (text or "").splitlines():
            ip = line.split("#")[0].strip()
            if ip:
                plcs[ip] = (user, per_plc_secrets.get(ip, default_pwd))

    for key, val in os.environ.items():
        m = re.match(r"^PLC_PASSWORDS_(\d+_\d+_\d+_\d+)$", key)
        if m:
            ip = m.group(1).replace("_", ".")
            plcs[ip] = (user, per_plc_secrets.get(ip) or val or default_pwd)

    for ip in password_overrides:
        if ip not in plcs:
            plcs[ip] = (user, per_plc_secrets.get(ip, default_pwd))

    return [(ip, u, p) for ip, (u, p) in plcs.items()]
