"""TT2 — L2 auth & middleware integration tests.

Drives ``_AuthMiddleware`` as a raw ASGI callable — no PLC, no network.

Approach summary
────────────────
Happy-path / 401 / dev-mode groups:
    Approach 1 — httpx.AsyncClient with ASGITransport.  Readable, close to real
    HTTP semantics, easy to assert status codes and JSON bodies.

Rate-limit / auth-failure-counter / per-IP groups:
    Approach 2 — hand-built ASGI scope/receive/send.  Needed because
    ASGITransport fixes scope["client"] to a single loopback address and
    provides no public API to override it.  Direct ASGI calls let us set
    scope["client"] to arbitrary (ip, port) tuples, which is exactly how
    _AuthMiddleware reads the client IP.

monotonic() patching:
    ``main.time`` is a reference to the ``time`` module object imported by
    main.py.  Monkeypatching ``main.time.monotonic`` redirects all calls
    inside the middleware without disturbing the real ``time`` module.
"""
import sys
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import httpx
import pytest
from loguru import logger

# Ensure src/ is on the path (mirrors the other unit test files)
_SRC = str(Path(__file__).parent.parent.parent / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import main  # noqa: E402
from main import _AuthMiddleware, _RATE_WINDOW, _RATE_LIMIT, _AUTH_ALERT, _APP_VERSION

# ─────────────────────────── shared helpers ───────────────────────────

_GOOD_KEY = "a" * 40   # 40 chars → passes _check_key_entropy (≥32)
_BAD_KEY  = "wrongkey" + "x" * 40


# ── minimal inner ASGI app (Approach 1 helper) ──────────────────────

class _InnerApp:
    """Trivial ASGI app that records whether it was reached and returns 200."""

    def __init__(self) -> None:
        self.called = False

    async def __call__(self, scope, receive, send) -> None:
        self.called = True
        await send({
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", b"application/json")],
        })
        await send({"type": "http.response.body", "body": b'{"inner":"ok"}'})


# ── ASGI scope / send helpers (Approach 2 helper) ───────────────────

def _make_scope(path: str, client_ip: str = "10.0.0.1", auth: str | None = None) -> dict:
    headers = []
    if auth is not None:
        headers.append((b"authorization", auth.encode("latin-1")))
    return {
        "type": "http",
        "method": "GET",
        "path": path,
        "query_string": b"",
        "headers": headers,
        "client": (client_ip, 12345),
    }


async def _null_receive():
    """No-op receive for ASGI calls that never read the body."""
    return {"type": "http.request", "body": b"", "more_body": False}


async def _drive(mw: _AuthMiddleware, scope: dict) -> dict:
    """Call the middleware directly and collect the response.

    Returns a dict with ``status``, ``headers`` (dict[str,str]), and ``body``.
    """
    messages: list[dict] = []

    async def _send(msg: dict) -> None:
        messages.append(msg)

    await mw(scope, _null_receive, _send)

    start = next(m for m in messages if m["type"] == "http.response.start")
    body_msg = next((m for m in messages if m["type"] == "http.response.body"), None)
    body = body_msg["body"] if body_msg else b""
    headers = {k.decode("latin-1"): v.decode("latin-1") for k, v in start.get("headers", [])}
    return {"status": start["status"], "headers": headers, "body": body}


# ─────────────────────────── fixtures ────────────────────────────────

@pytest.fixture()
def inner():
    """Fresh inner ASGI app per test."""
    return _InnerApp()


@pytest.fixture()
def mw(inner):
    """Fresh _AuthMiddleware with a known key, wrapping *inner*."""
    return _AuthMiddleware(inner, api_key=_GOOD_KEY)


@pytest.fixture()
def mw_dev(inner):
    """Fresh _AuthMiddleware in dev mode (api_key=''), wrapping *inner*."""
    return _AuthMiddleware(inner, api_key="")


@pytest.fixture()
def client(mw):
    """httpx AsyncClient with ASGITransport around *mw* (Approach 1)."""
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=mw), base_url="http://testserver")


@pytest.fixture()
def client_dev(mw_dev):
    """httpx AsyncClient wrapping dev-mode middleware."""
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=mw_dev), base_url="http://testserver")


@pytest.fixture()
def error_sink():
    """Capture ERROR (and above) loguru messages into a list."""
    captured: list[str] = []

    def _sink(message):
        if message.record["level"].name in ("ERROR", "CRITICAL"):
            captured.append(message.record["message"])

    sink_id = logger.add(_sink, level="ERROR", format="{message}")
    yield captured
    logger.remove(sink_id)


# ─────────────────────────── /health exemption ───────────────────────

class TestHealthExempt:
    """Approach 1: httpx + ASGITransport for readable HTTP assertions."""

    async def test_health_without_auth_header_returns_200(self, client) -> None:
        # Arrange: no Authorization header
        # Act
        resp = await client.get("/health")
        # Assert
        assert resp.status_code == 200

    async def test_health_with_auth_header_returns_200(self, client) -> None:
        # Arrange: correct Authorization header — still 200 (path is exempt)
        # Act
        resp = await client.get("/health", headers={"Authorization": f"Bearer {_GOOD_KEY}"})
        # Assert
        assert resp.status_code == 200

    async def test_health_body_has_status_ok(self, client) -> None:
        resp = await client.get("/health")
        body = resp.json()
        assert body["status"] == "ok"

    async def test_health_body_has_version(self, client) -> None:
        resp = await client.get("/health")
        body = resp.json()
        assert body["version"] == _APP_VERSION

    async def test_health_does_not_reach_inner_app(self, client, inner) -> None:
        await client.get("/health")
        assert not inner.called

    async def test_health_without_auth_does_not_decrement_rate_limit(self, mw) -> None:
        """Multiple /health requests must not consume rate-limit tokens."""
        # Drive 65 /health requests — more than _RATE_LIMIT — none should 429
        for _ in range(_RATE_LIMIT + 5):
            result = await _drive(mw, _make_scope("/health", auth=None))
            assert result["status"] == 200


# ─────────────────────────── /mcp auth enforcement ───────────────────

class TestMcpAuthEnforcement:
    """Approach 1: httpx for happy/401 paths; Approach 2 for header detail."""

    async def test_no_auth_header_returns_401(self, client) -> None:
        resp = await client.post("/mcp", content=b"{}")
        assert resp.status_code == 401

    async def test_wrong_bearer_returns_401(self, client) -> None:
        resp = await client.post("/mcp", content=b"{}", headers={"Authorization": f"Bearer {_BAD_KEY}"})
        assert resp.status_code == 401

    async def test_correct_bearer_passes_through_to_inner(self, client, inner) -> None:
        resp = await client.post("/mcp", content=b"{}", headers={"Authorization": f"Bearer {_GOOD_KEY}"})
        # Inner app returns 200
        assert resp.status_code == 200
        assert inner.called

    async def test_correct_bearer_inner_not_401(self, client) -> None:
        resp = await client.post("/mcp", content=b"{}", headers={"Authorization": f"Bearer {_GOOD_KEY}"})
        assert resp.status_code != 401

    async def test_401_response_has_www_authenticate_header(self, mw) -> None:
        # Approach 2: inspect raw headers directly
        scope = _make_scope("/mcp", auth=None)
        result = await _drive(mw, scope)
        assert result["status"] == 401
        # Header key is lowercase after our decode helper
        assert "www-authenticate" in result["headers"]

    async def test_401_body_is_json_unauthorized(self, client) -> None:
        resp = await client.post("/mcp", content=b"{}")
        assert resp.status_code == 401
        body = resp.json()
        assert "error" in body

    async def test_missing_bearer_prefix_returns_401(self, client) -> None:
        # Token sent without "Bearer " prefix — not a valid bearer token
        resp = await client.post("/mcp", content=b"{}", headers={"Authorization": _GOOD_KEY})
        assert resp.status_code == 401


# ─────────────────────────── dev mode (api_key="") ───────────────────

class TestDevMode:
    """api_key='' disables auth enforcement; all paths reach the inner app."""

    async def test_dev_mode_no_header_passes_through(self, client_dev, inner) -> None:
        resp = await client_dev.post("/mcp", content=b"{}")
        assert resp.status_code == 200
        assert inner.called

    async def test_dev_mode_wrong_header_still_passes_through(self, client_dev, inner) -> None:
        resp = await client_dev.post(
            "/mcp", content=b"{}", headers={"Authorization": f"Bearer {_BAD_KEY}"}
        )
        assert resp.status_code == 200
        assert inner.called

    async def test_dev_mode_health_still_returns_200(self, client_dev) -> None:
        resp = await client_dev.get("/health")
        assert resp.status_code == 200

    async def test_dev_mode_inner_reached_for_arbitrary_path(self, mw_dev, inner) -> None:
        scope = _make_scope("/some/other/path", auth=None)
        result = await _drive(mw_dev, scope)
        assert result["status"] == 200
        assert inner.called


# ─────────────────────────── rate limiting ───────────────────────────

class TestRateLimit:
    """
    Approach 2 (direct ASGI) throughout — we need to control scope["client"]
    per-call, and we monkeypatch main.time.monotonic to avoid sleeping.
    """

    def _mw_fresh(self) -> tuple[_AuthMiddleware, _InnerApp]:
        inner = _InnerApp()
        mw = _AuthMiddleware(inner, api_key=_GOOD_KEY)
        return mw, inner

    async def test_exactly_rate_limit_requests_succeed(self) -> None:
        # Arrange
        mw, _ = self._mw_fresh()
        scope = _make_scope("/mcp", client_ip="1.2.3.4", auth=f"Bearer {_GOOD_KEY}")
        t = 1000.0

        with patch.object(main.time, "monotonic", return_value=t):
            # Act: fire exactly _RATE_LIMIT requests
            statuses = []
            for _ in range(_RATE_LIMIT):
                result = await _drive(mw, scope)
                statuses.append(result["status"])

        # Assert: all 200 (inner app reached each time)
        assert all(s == 200 for s in statuses), f"unexpected non-200: {set(statuses)}"

    async def test_61st_request_returns_429(self) -> None:
        # Arrange
        mw, _ = self._mw_fresh()
        scope = _make_scope("/mcp", client_ip="1.2.3.4", auth=f"Bearer {_GOOD_KEY}")
        t = 1000.0

        with patch.object(main.time, "monotonic", return_value=t):
            for _ in range(_RATE_LIMIT):
                await _drive(mw, scope)
            # Act: one beyond the limit
            result = await _drive(mw, scope)

        # Assert
        assert result["status"] == 429

    async def test_429_has_retry_after_header(self) -> None:
        # Arrange
        mw, _ = self._mw_fresh()
        scope = _make_scope("/mcp", client_ip="1.2.3.4", auth=f"Bearer {_GOOD_KEY}")
        t = 1000.0

        with patch.object(main.time, "monotonic", return_value=t):
            for _ in range(_RATE_LIMIT):
                await _drive(mw, scope)
            result = await _drive(mw, scope)

        # Assert: retry-after header present
        assert "retry-after" in result["headers"], (
            f"retry-after missing from headers: {result['headers']}"
        )

    async def test_two_different_ips_bucketed_independently(self) -> None:
        # Arrange: exhaust the limit for IP A only
        mw, _ = self._mw_fresh()
        scope_a = _make_scope("/mcp", client_ip="1.1.1.1", auth=f"Bearer {_GOOD_KEY}")
        scope_b = _make_scope("/mcp", client_ip="2.2.2.2", auth=f"Bearer {_GOOD_KEY}")
        t = 1000.0

        with patch.object(main.time, "monotonic", return_value=t):
            for _ in range(_RATE_LIMIT):
                await _drive(mw, scope_a)
            # Act: 61st for A → 429
            result_a = await _drive(mw, scope_a)
            # Act: first for B → should NOT 429
            result_b = await _drive(mw, scope_b)

        # Assert
        assert result_a["status"] == 429
        assert result_b["status"] == 200

    async def test_window_reset_allows_new_requests(self) -> None:
        # Arrange: exhaust the limit at t=0, then advance time past _RATE_WINDOW
        mw, _ = self._mw_fresh()
        scope = _make_scope("/mcp", client_ip="3.3.3.3", auth=f"Bearer {_GOOD_KEY}")

        t_start = 1000.0
        with patch.object(main.time, "monotonic", return_value=t_start):
            for _ in range(_RATE_LIMIT):
                await _drive(mw, scope)
            result_over = await _drive(mw, scope)
        assert result_over["status"] == 429

        # Advance time beyond the window
        t_after = t_start + _RATE_WINDOW + 1.0
        with patch.object(main.time, "monotonic", return_value=t_after):
            # Act: first request in the new window
            result_reset = await _drive(mw, scope)

        # Assert: bucket was swept, request succeeds
        assert result_reset["status"] == 200


# ─────────────────────────── auth-failure counter & alert ────────────

class TestAuthFailureCounter:
    """Approach 2 (direct ASGI) — need per-call scope control for per-IP tracking."""

    def _mw_fresh(self) -> _AuthMiddleware:
        inner = _InnerApp()
        return _AuthMiddleware(inner, api_key=_GOOD_KEY)

    async def test_nine_failures_no_error_log(self, error_sink) -> None:
        # Arrange
        mw = self._mw_fresh()
        scope = _make_scope("/mcp", client_ip="5.5.5.5", auth=f"Bearer {_BAD_KEY}")

        # Act: 9 failures — one below the alert threshold
        for _ in range(_AUTH_ALERT - 1):
            await _drive(mw, scope)

        # Assert: no ERROR-level log entry
        assert error_sink == []

    async def test_10th_failure_triggers_error_alert(self, error_sink) -> None:
        # Arrange
        mw = self._mw_fresh()
        scope = _make_scope("/mcp", client_ip="5.5.5.5", auth=f"Bearer {_BAD_KEY}")

        # Act: exactly _AUTH_ALERT failures
        for _ in range(_AUTH_ALERT):
            await _drive(mw, scope)

        # Assert: at least one ERROR-level log line
        assert len(error_sink) >= 1, "Expected ERROR alert at 10th failure"

    async def test_error_alert_message_contains_ip(self, error_sink) -> None:
        mw = self._mw_fresh()
        ip = "5.5.5.5"
        scope = _make_scope("/mcp", client_ip=ip, auth=f"Bearer {_BAD_KEY}")

        for _ in range(_AUTH_ALERT):
            await _drive(mw, scope)

        assert any(ip in msg for msg in error_sink), (
            f"IP {ip!r} not found in error messages: {error_sink}"
        )

    async def test_failure_counter_resets_after_successful_auth(self, error_sink) -> None:
        # Arrange: build up 9 failures (one below alert)
        mw = self._mw_fresh()
        ip = "6.6.6.6"
        bad_scope  = _make_scope("/mcp", client_ip=ip, auth=f"Bearer {_BAD_KEY}")
        good_scope = _make_scope("/mcp", client_ip=ip, auth=f"Bearer {_GOOD_KEY}")

        for _ in range(_AUTH_ALERT - 1):
            await _drive(mw, bad_scope)

        # Act: one successful auth — resets the counter
        await _drive(mw, good_scope)
        assert mw._failures.get(ip, 0) == 0, "Counter should be 0 after successful auth"

        # Act: 9 more failures — should NOT trigger alert (counter started from 0)
        error_sink.clear()
        for _ in range(_AUTH_ALERT - 1):
            await _drive(mw, bad_scope)

        # Assert: still no alert (we only accumulated 9, not 10)
        assert error_sink == [], f"Unexpected ERROR after counter reset: {error_sink}"

    async def test_failures_from_different_ips_do_not_cross_contaminate(
        self, error_sink
    ) -> None:
        # Arrange: 9 failures from IP A and 9 from IP B — neither triggers alert
        mw = self._mw_fresh()
        scope_a = _make_scope("/mcp", client_ip="7.7.7.7", auth=f"Bearer {_BAD_KEY}")
        scope_b = _make_scope("/mcp", client_ip="8.8.8.8", auth=f"Bearer {_BAD_KEY}")

        for _ in range(_AUTH_ALERT - 1):
            await _drive(mw, scope_a)
            await _drive(mw, scope_b)

        # Assert: separate counters, no alert yet
        assert mw._failures.get("7.7.7.7", 0) == _AUTH_ALERT - 1
        assert mw._failures.get("8.8.8.8", 0) == _AUTH_ALERT - 1
        assert error_sink == []

    async def test_alert_fires_on_subsequent_failures_past_threshold(
        self, error_sink
    ) -> None:
        """Failures beyond _AUTH_ALERT also log ERROR (not just exactly the 10th)."""
        mw = self._mw_fresh()
        scope = _make_scope("/mcp", client_ip="9.9.9.9", auth=f"Bearer {_BAD_KEY}")

        for _ in range(_AUTH_ALERT + 3):
            await _drive(mw, scope)

        # Every call at or above _AUTH_ALERT logs ERROR → at least 4 messages
        assert len(error_sink) >= 4
