"""URL-construction + response-parsing tests for the 2026-09-11 WDA coverage
expansion (device features, feature composition, method-run listing, single
in/out-args, class instances, File API). Same respx-at-the-boundary pattern
as test_wda_client.py — no PLC required.
"""
import httpx
import respx

from wda_client import WDAClient

IP = "1.2.3.4"
BASE = f"https://{IP}"


def _client() -> WDAClient:
    c = WDAClient(IP, "admin", "pw", timeout=5.0)
    c._token = ""  # Basic Auth mode, skip token acquisition
    return c


@respx.mock
async def test_get_device_features_hits_devices_subpath():
    respx.get(f"{BASE}/wda/devices/0-0").mock(
        return_value=httpx.Response(200, json={"data": {"id": "0-0", "attributes": {}}})
    )
    respx.get(url__regex=rf"{BASE}/wda/devices/0-0/features.*").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "f1"}, {"id": "f2"}]})
    )
    client = _client()
    try:
        device = await client.get_device("0-0")
        features = await client.get_device_features("0-0")
    finally:
        await client.close()
    assert device["id"] == "0-0"
    assert [f["id"] for f in features] == ["f1", "f2"]


@respx.mock
async def test_feature_composition_hits_three_distinct_subpaths():
    respx.get(url__regex=rf"{BASE}/wda/features/f1/includedfeatures.*").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "f2"}]})
    )
    respx.get(url__regex=rf"{BASE}/wda/features/f1/containedparameters.*").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "p1"}]})
    )
    respx.get(url__regex=rf"{BASE}/wda/features/f1/containedmethods.*").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "m1"}]})
    )
    client = _client()
    try:
        included = await client.get_feature_included_features("f1")
        params = await client.get_feature_contained_parameters("f1")
        methods = await client.get_feature_contained_methods("f1")
    finally:
        await client.close()
    assert [i["id"] for i in included] == ["f2"]
    assert [p["id"] for p in params] == ["p1"]
    assert [m["id"] for m in methods] == ["m1"]


@respx.mock
async def test_single_inarg_outarg_and_run_list():
    respx.get(f"{BASE}/wda/method-definitions/m1/inargs/newvalue").mock(
        return_value=httpx.Response(200, json={"data": {"id": "newvalue", "attributes": {"dataType": "uint32"}}})
    )
    respx.get(f"{BASE}/wda/method-definitions/m1/outargs/result").mock(
        return_value=httpx.Response(200, json={"data": {"id": "result", "attributes": {"dataType": "boolean"}}})
    )
    respx.get(url__regex=rf"{BASE}/wda/methods/m1/runs\?.*").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "1"}, {"id": "2"}]})
    )
    client = _client()
    try:
        inarg = await client.get_method_inarg("m1", "newvalue")
        outarg = await client.get_method_outarg("m1", "result")
        runs = await client.list_method_runs("m1")
    finally:
        await client.close()
    assert inarg["id"] == "newvalue"
    assert outarg["id"] == "result"
    assert [r["id"] for r in runs] == ["1", "2"]


@respx.mock
async def test_parameter_instance_chain_hits_all_four_subpaths():
    respx.get(f"{BASE}/wda/parameters/p1/instances/3").mock(
        return_value=httpx.Response(200, json={"data": {"id": "3", "attributes": {}}})
    )
    respx.get(f"{BASE}/wda/parameters/p1/instances/3/device").mock(
        return_value=httpx.Response(200, json={"data": {"id": "0-0"}})
    )
    respx.get(url__regex=rf"{BASE}/wda/parameters/p1/instances/3/parameters.*").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "ip1"}]})
    )
    respx.get(url__regex=rf"{BASE}/wda/parameters/p1/instances/3/methods.*").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "im1"}]})
    )
    client = _client()
    try:
        instance = await client.get_parameter_instance("p1", "3")
        device = await client.get_parameter_instance_device("p1", "3")
        params = await client.get_parameter_instance_parameters("p1", "3")
        methods = await client.get_parameter_instance_methods("p1", "3")
    finally:
        await client.close()
    assert instance["id"] == "3"
    assert device["id"] == "0-0"
    assert [p["id"] for p in params] == ["ip1"]
    assert [m["id"] for m in methods] == ["im1"]


@respx.mock
async def test_file_api_create_upload_download_metadata():
    respx.post(url__regex=rf"{BASE}/files\?.*").mock(
        return_value=httpx.Response(201, json={"data": {"id": "file-42"}})
    )
    respx.put(f"{BASE}/files/file-42").mock(return_value=httpx.Response(204))
    respx.get(f"{BASE}/files/file-42").mock(
        return_value=httpx.Response(200, content=b"hello")
    )
    respx.head(f"{BASE}/files/file-42").mock(
        return_value=httpx.Response(200, headers={"Content-Length": "5", "Content-Type": "text/plain"})
    )
    client = _client()
    try:
        file_id = await client.create_file("0-0-somefileparam")
        upload_result = await client.upload_file(file_id, b"hello", "text/plain")
        content = await client.download_file(file_id)
        meta = await client.get_file_metadata(file_id)
    finally:
        await client.close()
    assert file_id == "file-42"
    assert upload_result == {"status": "ok"}
    assert content == b"hello"
    assert meta["content-length"] == "5"
