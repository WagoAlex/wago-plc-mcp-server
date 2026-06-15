"""Unified logging via loguru. Intercepts stdlib logging from httpx, uvicorn, mcp."""
import logging
import logging.handlers
import socket
import sys
from loguru import logger


class InterceptHandler(logging.Handler):
    """Route stdlib logging records into loguru."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1
        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def setup_logging(log_file: str = "/app/mcp_server.log", level: str = "INFO") -> None:
    """Single logger, single format, no duplicates. AUDIT entries go to the audit log only.

    File budget: 10 MB × 3 rotated files = 30 MB max on-disk.
    """
    logger.remove()

    fmt = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <7}</level> | "
        "<cyan>{name}:{function}:{line}</cyan> | "
        "{message}"
    )

    _not_audit = lambda r: r["level"].name != "AUDIT"

    logger.add(sys.stderr, format=fmt, level=level, colorize=True, enqueue=False, filter=_not_audit)
    logger.add(
        log_file,
        format=fmt,
        level=level,
        rotation="10 MB",
        retention=3,
        enqueue=True,
        backtrace=False,
        diagnose=False,
        filter=_not_audit,
    )

    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
    for name in (
        "uvicorn", "uvicorn.access", "uvicorn.error",
        "httpx", "httpcore", "asyncio", "mcp",
    ):
        lg = logging.getLogger(name)
        lg.handlers = [InterceptHandler()]
        lg.propagate = False

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def setup_audit_logging(
    audit_log_file: str = "/app/audit.log",
    syslog_host: str | None = None,
    syslog_port: int = 514,
    syslog_tcp: bool = False,
) -> None:
    """Add a JSON-lines sink for AUDIT-level entries, with optional syslog/SIEM export.

    Local file budget:
      - syslog active   → 10 MB × 2 files = 20 MB  (SIEM is authoritative copy)
      - syslog inactive → 10 MB × 5 files = 50 MB

    Syslog: enabled when syslog_host is set. Uses UDP by default; pass syslog_tcp=True
    for TCP. Note: syslog truncates messages >2 KB (RFC 5424) — long parameter lists
    may be clipped at the receiver.
    """
    try:
        logger.level("AUDIT")
    except ValueError:
        logger.level("AUDIT", no=25, color="<yellow>", icon="AUDIT")

    _audit_only = lambda r: r["level"].name == "AUDIT"
    local_retention = 2 if syslog_host else 5

    logger.add(
        audit_log_file,
        level="AUDIT",
        format="{message}\n",
        filter=_audit_only,
        rotation="10 MB",
        retention=local_retention,
        enqueue=True,
        backtrace=False,
        diagnose=False,
    )

    if syslog_host:
        socktype = socket.SOCK_STREAM if syslog_tcp else socket.SOCK_DGRAM
        try:
            handler = logging.handlers.SysLogHandler(
                address=(syslog_host, syslog_port),
                socktype=socktype,
            )
            logger.add(
                handler,
                level="AUDIT",
                format="{message}",
                filter=_audit_only,
            )
            proto = "TCP" if syslog_tcp else "UDP"
            logger.info(f"[audit] Syslog export → {syslog_host}:{syslog_port} ({proto}), local retention reduced to {local_retention} files")
        except Exception as e:
            logger.warning(f"[audit] Syslog setup failed ({syslog_host}:{syslog_port}): {e} — local file only")
