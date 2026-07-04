"""get_parameters_bulk concurrency bound (#19) — importing main boots the FastMCP
app (no server), so these run without a PLC or network."""
import asyncio

import main
from plc_manager import PLCEntry


class _CountingClient:
    """Stub WDA client that tracks peak concurrent get_parameter calls."""

    def __init__(self):
        self.active = 0
        self.peak = 0

    async def get_parameter(self, pid: str) -> dict:
        self.active += 1
        self.peak = max(self.peak, self.active)
        await asyncio.sleep(0.01)  # force overlap so the bound is observable
        self.active -= 1
        return {"value": 1, "dataType": "number"}


async def test_bulk_reads_respect_concurrency_bound(monkeypatch):
    monkeypatch.setenv("WAGO_MAX_CONCURRENT_READS", "3")
    stub = _CountingClient()
    entry = PLCEntry(ip="9.9.9.9", client=stub)
    entry.parameters = {f"p{i}" for i in range(20)}
    monkeypatch.setitem(main.plc_manager.plcs, "9.9.9.9", entry)

    requests = [{"plc_ip": "9.9.9.9", "parameter_id": f"p{i}"} for i in range(20)]
    results = await main.get_parameters_bulk(ctx=None, requests=requests)

    assert len(results) == 20
    assert all("error" not in r for r in results)
    assert stub.peak <= 3


async def test_bulk_reads_report_per_item_errors(monkeypatch):
    stub = _CountingClient()
    entry = PLCEntry(ip="9.9.9.9", client=stub)
    entry.parameters = {"known"}
    monkeypatch.setitem(main.plc_manager.plcs, "9.9.9.9", entry)

    results = await main.get_parameters_bulk(ctx=None, requests=[
        {"plc_ip": "9.9.9.9", "parameter_id": "known"},
        {"plc_ip": "9.9.9.9", "parameter_id": "nope"},
        {"plc_ip": "8.8.8.8", "parameter_id": "known"},
    ])
    assert "error" not in results[0]
    assert "Unknown parameter" in results[1]["error"]
    assert "not registered" in results[2]["error"]
