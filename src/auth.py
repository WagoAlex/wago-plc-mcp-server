"""MCP endpoint authentication: API key lifecycle + ASGI bearer-auth middleware.

Extracted from main.py. The middleware also applies per-IP rate limiting and
alerts on repeated auth failures. /health stays unauthenticated for the
docker-compose healthcheck.
"""
import importlib.metadata
import json
import os
import secrets as _secrets
import time
from collections import deque
from pathlib import Path

from loguru import logger

from config import read_secret

KEY_PATH = Path("/app/data/mcp_api_key")
MIN_KEY_LENGTH = 32  # 128-bit minimum (characters); auto-gen produces 64

RATE_WINDOW = 60.0   # seconds
RATE_LIMIT   = 60    # max requests per IP per window
AUTH_ALERT   = 10    # failed auth attempts before ERROR alert
MAX_TRACKED_IPS = 10_000  # cap on per-IP state entries (pre-auth memory DoS guard)

try:
    APP_VERSION = importlib.metadata.version("wago-plc-mcp-server")
except importlib.metadata.PackageNotFoundError:
    APP_VERSION = "unknown"


def _check_key_entropy(key: str, source: str) -> None:
    """Abort startup if a supplied API key is shorter than the minimum length."""
    if len(key) < MIN_KEY_LENGTH:
        logger.error(
            f"[auth] API key from {source} is too short "
            f"({len(key)} chars, minimum {MIN_KEY_LENGTH}). "
            f"Generate a strong key:  openssl rand -hex 32"
        )
        raise SystemExit(1)


def resolve_api_key() -> tuple[str, bool]:
    """Resolve the MCP API key, auto-generating one if none is configured.

    Priority:
      1. Docker Secret  /run/secrets/mcp_api_key  (prod — highest trust)
      2. Env var        MCP_API_KEY                (dev override)
      3. Persisted file /app/data/mcp_api_key      (auto-generated, volume-backed)
      4. Generate new → persist to /app/data/mcp_api_key

    Supplied keys (paths 1-3) must be at least MIN_KEY_LENGTH chars; shorter
    keys abort startup with SystemExit(1).

    Returns (api_key, is_newly_generated).
    """
    key = read_secret("mcp_api_key")
    if key:
        _check_key_entropy(key, "Docker Secret mcp_api_key")
        return key, False

    key = os.getenv("MCP_API_KEY", "").strip()
    if key:
        _check_key_entropy(key, "env var MCP_API_KEY")
        return key, False

    if KEY_PATH.exists():
        key = KEY_PATH.read_text().strip()
        if key:
            _check_key_entropy(key, f"persisted file {KEY_PATH}")
            return key, False

    key = _secrets.token_hex(32)
    try:
        KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
        KEY_PATH.write_text(key)
    except OSError as e:
        logger.warning(f"[auth] Could not persist generated key ({e}) — key resets on restart; mount ./data:/app/data")
    return key, True


def print_key_banner(key: str) -> None:
    """Announce a newly generated key WITHOUT echoing it.

    stdout is persisted by Docker's json-file log driver, so anything printed
    here is readable via `docker logs wmcp` for the container's lifetime -
    only a fingerprint and the retrieval command are safe to show.
    """
    sep = "=" * 72
    print(f"""
{sep}
  NEW MCP API KEY GENERATED  (fingerprint: {key[:8]}…)

  Stored in ./data/mcp_api_key - retrieve it with:
    docker exec wmcp cat /app/data/mcp_api_key

  .mcp.json:
    "headers": {{"Authorization": "Bearer <key>"}}

  Regenerate:  docker exec wmcp python src/mcp_keygen.py
{sep}
""", flush=True)
    logger.info(f"[auth] New API key (fingerprint {key[:8]}) persisted to {KEY_PATH}")


class AuthMiddleware:
    """ASGI middleware: serves /health unauthenticated; enforces Bearer auth on all other paths.

    Also applies per-IP rate limiting and alerts on repeated auth failures.
    When api_key is empty, auth enforcement is disabled (dev mode) but /health still works.
    """

    _HEALTH    = json.dumps({"status": "ok", "version": APP_VERSION}).encode()
    _UNAUTH    = b'{"error":"Unauthorized"}'
    _RATE_BODY = b'{"error":"Too Many Requests"}'

    def __init__(self, app, api_key: str) -> None:
        self._app = app
        # None signals "auth disabled — pass all traffic through"
        self._key: bytes | None = api_key.encode() if api_key else None
        self._rate: dict[str, deque] = {}
        self._failures: dict[str, int] = {}

    def _evict_stale(self, now: float) -> None:
        """Bound per-IP state so unauthenticated scanners can't grow memory forever.

        Cheap path: nothing to do below the cap. Above it, drop rate buckets whose
        newest entry is outside the window (their state is semantically empty) and,
        if _failures alone exceeds the cap, clear it wholesale - losing failure
        counters under active flooding only delays the ALERT log line, it never
        weakens auth itself.
        """
        if len(self._rate) > MAX_TRACKED_IPS:
            self._rate = {
                ip: bucket for ip, bucket in self._rate.items()
                if bucket and now - bucket[-1] <= RATE_WINDOW
            }
        if len(self._failures) > MAX_TRACKED_IPS:
            self._failures.clear()

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        if scope.get("path") == "/health":
            await send({"type": "http.response.start", "status": 200,
                        "headers": [(b"content-type", b"application/json"),
                                    (b"content-length", str(len(self._HEALTH)).encode())]})
            await send({"type": "http.response.body", "body": self._HEALTH})
            return

        ip: str = (scope.get("client") or ("", 0))[0]

        # Rate limit
        now = time.monotonic()
        self._evict_stale(now)
        bucket = self._rate.setdefault(ip, deque())
        while bucket and now - bucket[0] > RATE_WINDOW:
            bucket.popleft()
        if len(bucket) >= RATE_LIMIT:
            logger.warning(f"[auth] rate limit exceeded for {ip}")
            await send({"type": "http.response.start", "status": 429,
                        "headers": [(b"content-type", b"application/json"),
                                    (b"content-length", str(len(self._RATE_BODY)).encode()),
                                    (b"retry-after", b"60")]})
            await send({"type": "http.response.body", "body": self._RATE_BODY})
            return
        bucket.append(now)

        if self._key is not None:
            headers = {k.lower(): v for k, v in scope.get("headers", [])}
            auth = headers.get(b"authorization", b"").decode("latin-1")
            token = auth[7:] if auth.startswith("Bearer ") else ""

            if not _secrets.compare_digest(token.encode(), self._key):
                self._failures[ip] = self._failures.get(ip, 0) + 1
                count = self._failures[ip]
                if count >= AUTH_ALERT:
                    logger.error(f"[auth] ALERT — {count} failed attempts from {ip}")
                else:
                    logger.warning(f"[auth] rejected {scope.get('method','?')} {scope.get('path','?')} from {ip}")
                await send({"type": "http.response.start", "status": 401,
                            "headers": [(b"content-type", b"application/json"),
                                        (b"content-length", str(len(self._UNAUTH)).encode()),
                                        (b"www-authenticate", b"Bearer")]})
                await send({"type": "http.response.body", "body": self._UNAUTH})
                return

            self._failures.pop(ip, None)  # reset on successful auth

        await self._app(scope, receive, send)
