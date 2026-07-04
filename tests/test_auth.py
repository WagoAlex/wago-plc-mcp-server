"""Unit tests for the ASGI auth middleware + API key lifecycle (src/auth.py)."""
import auth
from auth import AuthMiddleware

API_KEY = "k" * 64


def _scope(path="/mcp", ip="1.2.3.4", token=None):
    headers = []
    if token is not None:
        headers.append((b"authorization", f"Bearer {token}".encode()))
    return {
        "type": "http",
        "path": path,
        "method": "POST",
        "client": (ip, 12345),
        "headers": headers,
    }


class _Recorder:
    def __init__(self):
        self.messages = []

    async def __call__(self, msg):
        self.messages.append(msg)

    @property
    def status(self):
        return self.messages[0]["status"]

    @property
    def body(self):
        return b"".join(m.get("body", b"") for m in self.messages if m["type"] == "http.response.body")


async def _app(scope, receive, send):
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"app"})


async def _receive():  # pragma: no cover — never called by the middleware
    return {"type": "http.request"}


async def test_health_is_unauthenticated():
    mw = AuthMiddleware(_app, API_KEY)
    send = _Recorder()
    await mw(_scope(path="/health"), _receive, send)
    assert send.status == 200
    assert b'"status": "ok"' in send.body


async def test_wrong_token_rejected_401():
    mw = AuthMiddleware(_app, API_KEY)
    send = _Recorder()
    await mw(_scope(token="wrong"), _receive, send)
    assert send.status == 401


async def test_missing_header_rejected_401():
    mw = AuthMiddleware(_app, API_KEY)
    send = _Recorder()
    await mw(_scope(), _receive, send)
    assert send.status == 401


async def test_correct_token_passes_through():
    mw = AuthMiddleware(_app, API_KEY)
    send = _Recorder()
    await mw(_scope(token=API_KEY), _receive, send)
    assert send.status == 200
    assert send.body == b"app"


async def test_empty_key_disables_auth_dev_mode():
    mw = AuthMiddleware(_app, "")
    send = _Recorder()
    await mw(_scope(), _receive, send)
    assert send.status == 200


async def test_rate_limit_429_after_burst():
    mw = AuthMiddleware(_app, API_KEY)
    for _ in range(auth.RATE_LIMIT):
        await mw(_scope(token=API_KEY), _receive, _Recorder())
    send = _Recorder()
    await mw(_scope(token=API_KEY), _receive, send)
    assert send.status == 429


async def test_failure_counter_resets_on_success():
    mw = AuthMiddleware(_app, API_KEY)
    await mw(_scope(token="wrong"), _receive, _Recorder())
    assert mw._failures["1.2.3.4"] == 1
    await mw(_scope(token=API_KEY), _receive, _Recorder())
    assert "1.2.3.4" not in mw._failures


async def test_per_ip_state_is_bounded(monkeypatch):
    """Scanner cycling IPs must not grow middleware state without bound (#17)."""
    monkeypatch.setattr(auth, "MAX_TRACKED_IPS", 5)
    mw = AuthMiddleware(_app, API_KEY)

    # Stale rate buckets (outside the window) get evicted once past the cap
    from collections import deque
    for i in range(20):
        mw._rate[f"10.0.0.{i}"] = deque([-1000.0])  # monotonic long ago
        mw._failures[f"10.0.0.{i}"] = 3

    await mw(_scope(ip="10.9.9.9", token=API_KEY), _receive, _Recorder())
    assert len(mw._rate) <= 6      # fresh requester + nothing stale
    assert len(mw._failures) <= 5  # cleared wholesale past the cap


def test_resolve_api_key_rejects_short_key(monkeypatch):
    import pytest
    monkeypatch.setenv("MCP_API_KEY", "short")
    with pytest.raises(SystemExit):
        auth.resolve_api_key()


def test_print_key_banner_never_echoes_key(capsys):
    """#21: the full key must not reach stdout (docker logs persist it)."""
    key = "deadbeef" + "a" * 56
    auth.print_key_banner(key)
    out = capsys.readouterr().out
    assert key not in out
    assert key[:8] in out  # fingerprint only
