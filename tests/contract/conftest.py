"""Contract-test fixtures: respx cassette router for each PLC class.

Design notes
────────────
- Cassettes live in tests/cassettes/<class>/*.json.  Each file has a ``_meta``
  key (ignored at runtime) plus ``status``, ``headers``, and ``body``.
- respx intercepts httpx globally, so WDAClient's internal AsyncClient is caught
  without any injection plumbing.
- The token GET (/wda) is matched unconditionally on path — it must come first in
  the route list so that both ping() (Basic Auth, no query) and _acquire_token()
  (Basic Auth, first request) resolve to the same cassette.
- Paginated endpoints: respx matches on URL path only (respx.route(url=...)) and
  we capture the ``next`` link verbatim from the cassette.  The second page is
  served by a separate cassette whose path matches the next URL.
- Fake IP used in all tests: 10.99.99.1 (CC100), 10.99.99.2 (Edge),
  10.99.99.3 (PFC200).  These are never routable.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import respx
import httpx

# ── cassette loader ──────────────────────────────────────────────────────────

_CASSETTES = Path(__file__).parent.parent / "cassettes"


def _load(cls: str, name: str) -> dict:
    """Load tests/cassettes/<cls>/<name>.json and return its content dict."""
    path = _CASSETTES / cls / f"{name}.json"
    with path.open() as fh:
        return json.load(fh)


def _resp(cassette: dict, body_key: str = "body") -> httpx.Response:
    """Build an httpx.Response from cassette fields (status / headers / body)."""
    return httpx.Response(
        status_code=cassette["status"],
        headers=cassette.get("headers", {}),
        json=cassette[body_key],
    )


# ── fake IPs (never routable) ────────────────────────────────────────────────

CC100_IP   = "10.99.99.1"
EDGE_IP    = "10.99.99.2"
PFC200_IP  = "10.99.99.3"

FAKE_USER = "admin"
FAKE_PASS = "FAKE_PASSWORD_NOT_REAL"


# ── helpers to wire a class cassette into a respx.MockRouter ────────────────

def _wire_class(router: respx.MockRouter, ip: str, cls: str) -> None:
    """Register all WDA routes for *cls* into *router* pointed at *ip*."""
    base = f"https://{ip}"

    si = _load(cls, "service_identity")
    p1 = _load(cls, "parameters_page1")
    pd = _load(cls, "parameter_definitions")
    dev = _load(cls, "devices")
    feat = _load(cls, "features")
    meth = _load(cls, "methods")
    enum_d = _load(cls, "enum_definitions")

    # ── Service identity / ping / token acquisition ──────────────────────────
    # Match GET /wda exactly (no query string on this path).
    router.get(f"{base}/wda").mock(return_value=_resp(si))

    # ── Parameters (paginated) ───────────────────────────────────────────────
    # Page 1: first URL the client builds (path + query params).
    # We match on URL pattern; respx matches regardless of query order.
    page1_pattern = f"{base}/wda/parameters"
    if cls == "edge":
        # Edge has two pages.  Serve page 1 when offset=0 is absent or =0,
        # page 2 when offset=500.
        p2 = _load(cls, "parameters_page2")
        router.get(
            url__regex=rf"^{re_escape(base)}/wda/parameters\?.*page\[offset\]=500.*$"
        ).mock(return_value=_resp(p2))
        router.get(
            url__regex=rf"^{re_escape(base)}/wda/parameters\?.*$"
        ).mock(return_value=_resp(p1))
    else:
        router.get(
            url__regex=rf"^{re_escape(base)}/wda/parameters\?.*$"
        ).mock(return_value=_resp(p1))

    # ── Parameter definitions ────────────────────────────────────────────────
    router.get(
        url__regex=rf"^{re_escape(base)}/wda/parameter-definitions\?.*$"
    ).mock(return_value=_resp(pd))

    # ── Devices ──────────────────────────────────────────────────────────────
    router.get(
        url__regex=rf"^{re_escape(base)}/wda/devices\?.*$"
    ).mock(return_value=_resp(dev))

    # ── Features ─────────────────────────────────────────────────────────────
    router.get(
        url__regex=rf"^{re_escape(base)}/wda/features\?.*$"
    ).mock(return_value=_resp(feat))

    # ── Methods ──────────────────────────────────────────────────────────────
    router.get(
        url__regex=rf"^{re_escape(base)}/wda/methods\?.*$"
    ).mock(return_value=_resp(meth))

    # ── Enum definitions ─────────────────────────────────────────────────────
    router.get(
        url__regex=rf"^{re_escape(base)}/wda/enum-definitions\?.*$"
    ).mock(return_value=_resp(enum_d))


def re_escape(s: str) -> str:
    """Escape dots in an IP/base URL for use in a regex pattern."""
    return s.replace(".", r"\.")


# ── per-class fixtures ────────────────────────────────────────────────────────


@pytest.fixture()
async def cc100_router():
    """respx router pre-wired with CC100 cassettes (includes token header)."""
    with respx.mock(assert_all_called=False) as router:
        _wire_class(router, CC100_IP, "cc100")
        yield router


@pytest.fixture()
async def edge_router():
    """respx router pre-wired with Edge cassettes (2-page parameters, no token)."""
    with respx.mock(assert_all_called=False) as router:
        _wire_class(router, EDGE_IP, "edge")
        yield router


@pytest.fixture()
async def pfc200_router():
    """respx router pre-wired with PFC200 cassettes."""
    with respx.mock(assert_all_called=False) as router:
        _wire_class(router, PFC200_IP, "pfc200")
        yield router


# ── invoke_method run fixtures (used by CT-06) ────────────────────────────────

def _make_run_router(ip: str, cls: str, run_cassette: str) -> respx.MockRouter:
    """Return a started respx.mock context with /wda + /runs wired."""
    router = respx.mock(assert_all_called=False)
    router.start()
    base = f"https://{ip}"

    si = _load(cls, "service_identity")
    router.get(f"{base}/wda").mock(return_value=_resp(si))

    run = _load(cls, run_cassette)
    router.post(
        url__regex=rf"^{re_escape(base)}/wda/methods/.+/runs.*$"
    ).mock(return_value=_resp(run))
    return router


@pytest.fixture()
async def cc100_run_done_router():
    router = _make_run_router(CC100_IP, "cc100", "method_run_done")
    yield router
    router.stop()


@pytest.fixture()
async def cc100_run_progress_router():
    router = _make_run_router(CC100_IP, "cc100", "method_run_progress")
    yield router
    router.stop()


@pytest.fixture()
async def cc100_run_error_router():
    router = _make_run_router(CC100_IP, "cc100", "method_run_error")
    yield router
    router.stop()
