"""Contract tests against captured FW31 WDA cassettes (docs/*-fw31-parameters-raw.json).

Verifies the client's pagination + ID extraction against real device payloads
without a live PLC. Cassettes are single JSON:API pages captured with
parameter-errors-as-data-attributes=true.
"""
import json
from pathlib import Path

import httpx
import pytest
import respx

from plc_manager import KNOWN_PARAM_COUNTS
from wda_client import WDAClient

DOCS = Path(__file__).parent.parent / "docs"

CASSETTES = {
    "PFC200": "pfc200-fw31-parameters-raw.json",
    "CC100": "cc100-fw31-parameters-raw.json",
    "PFC300": "pfc300-fw31-parameters-raw.json",
    "Edge": "edge-fw31-parameters-raw.json",
}


@pytest.mark.parametrize("device_class,filename", CASSETTES.items())
@respx.mock
async def test_cassette_parameters_register_completely(device_class, filename):
    cassette = DOCS / filename
    if not cassette.exists():
        pytest.skip(f"cassette {filename} not present in image")

    body = json.loads(cassette.read_text())
    respx.get(url__regex=r"https://9\.9\.9\.9/wda/parameters.*").mock(
        return_value=httpx.Response(200, json={"data": body["data"], "links": {}})
    )

    client = WDAClient("9.9.9.9", "admin", "pw", timeout=5.0)
    client._token = ""
    try:
        items = await client.list_parameters()
    finally:
        await client.close()

    ids = {item["id"] for item in items if "id" in item}
    assert len(ids) == len(items), "duplicate parameter IDs in cassette sweep"
    # Floor check, same semantics as describe_plc's parameter_count_ok
    assert len(ids) >= KNOWN_PARAM_COUNTS[device_class]
