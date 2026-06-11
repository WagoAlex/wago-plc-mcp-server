"""Unified logging via loguru. Intercepts stdlib logging from httpx, uvicorn, mcp."""
import logging
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
    """Single logger, single format, no duplicates. AUDIT entries go to the audit log only."""
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
        retention=5,
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


def setup_audit_logging(audit_log_file: str = "/app/audit.log") -> None:
    """Add a separate JSON-lines sink that receives only AUDIT-level entries."""
    try:
        logger.level("AUDIT")
    except ValueError:
        logger.level("AUDIT", no=25, color="<yellow>", icon="AUDIT")

    logger.add(
        audit_log_file,
        level="AUDIT",
        format="{message}\n",
        filter=lambda r: r["level"].name == "AUDIT",
        rotation="50 MB",
        retention=10,
        enqueue=True,
        backtrace=False,
        diagnose=False,
    )
