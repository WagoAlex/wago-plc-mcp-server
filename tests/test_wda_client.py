"""Unit tests for WDAClient pagination and token refresh (src/wda_client.py).

httpx is mocked with respx at the client boundary — no PLC required.
"""
import asyncio
import json

import httpx
import pytest
import respx

from wda_client import WDAClient

IP = "1.2.3.4"
BASE = f"https://{IP}"
JSON_API = {"Content-Type": "application/vnd.api+json"}


def _client(page_limit=500) -> WDAClient:
    c = WDAClient(IP, "admin", "pw", timeout=5.0, page_limit=page_limit)
    c._token = ""  # skip token acquisition — Basic Auth mode
    return c


def _items(start, count):
    return [{"id": f"param-{i}", "type": "parameters"} for i in range(start, start + count)]


# ── pagination (#16) ──

@respx.mock
async def test_paginate_follows_links_next_despite_255_cap():
    """WDA caps pages at 255 regardless of page[limit]; a short page with a
    links.next present must NOT end the walk."""
    def responder(request):
        offset = int(request.url.params.get("page[offset]", "0"))
        if offset == 0:
            body = {"data": _items(0, 255),
                    "links": {"next": "/wda/parameters?parameter-errors-as-data-attributes=true"
                                      "&page[limit]=500&page[offset]=255"}}
        else:
            body = {"data": _items(255, 143), "links": {}}
        return httpx.Response(200, json=body)

    respx.get(url__regex=rf"{BASE}/wda/parameters.*").mock(side_effect=responder)

    client = _client(page_limit=500)
    try:
        items = await client.list_parameters()
    finally:
        await client.close()
    assert len(items) == 398  # 255 + 143 — nothing silently dropped


@respx.mock
async def test_paginate_stops_on_missing_links_next():
    respx.get(url__regex=rf"{BASE}/wda/parameters.*").mock(
        return_value=httpx.Response(200, json={"data": _items(0, 42), "links": {}})
    )
    client = _client()
    try:
        items = await client.list_parameters()
    finally:
        await client.close()
    assert len(items) == 42


@respx.mock
async def test_paginate_empty_page_with_corrupt_links_next_terminates():
    """A links.next that keeps yielding empty pages must not loop forever."""
    respx.get(url__regex=rf"{BASE}/wda/parameters.*").mock(
        return_value=httpx.Response(200, json={
            "data": [],
            "links": {"next": "/wda/parameters?page[limit]=500&page[offset]=0"},
        })
    )
    client = _client()
    try:
        items = await asyncio.wait_for(client.list_parameters(), timeout=5)
    finally:
        await client.close()
    assert items == []


# ── token refresh (#20) ──

@respx.mock
async def test_concurrent_401s_reauthenticate_once():
    auth_calls = 0

    def auth_endpoint(request):
        nonlocal auth_calls
        auth_calls += 1
        return httpx.Response(200, headers={"WAGO-WDX-Auth-Token": "fresh"})

    def data_endpoint(request):
        if request.headers.get("Authorization") == "Bearer stale":
            return httpx.Response(401)
        return httpx.Response(200, json={"data": {"attributes": {"value": 1}}})

    respx.get(f"{BASE}/wda").mock(side_effect=auth_endpoint)
    respx.get(url__regex=rf"{BASE}/wda/parameters/.*").mock(side_effect=data_endpoint)

    client = WDAClient(IP, "admin", "pw", timeout=5.0)
    client._token = "stale"
    try:
        results = await asyncio.gather(
            client.get_parameter("p1"), client.get_parameter("p2")
        )
    finally:
        await client.close()

    assert all(r == {"value": 1} for r in results)
    assert auth_calls == 1  # double-checked refresh: second coroutine reuses fresh token
