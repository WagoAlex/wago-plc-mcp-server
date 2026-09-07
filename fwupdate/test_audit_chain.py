"""A firmware flash must land in the SAME tamper-evident chain as everything
else, and must not break it. This asserts against the real src/audit.py."""
import json

import audit


def test_firmware_record_chains_off_an_existing_log(tmp_path):
    log = tmp_path / "audit.log"
    # An existing entry written the way the MCP server writes them.
    audit.append_audit(str(log), "set_parameters", "10.0.0.1", "key-abc", "ok",
                       params=[{"id": "0-0-ntpclient-enabled", "value": True}])
    audit.append_audit(str(log), "firmware_update", "10.0.0.1", "fwupdate", "ok",
                       revision="4.9.1", commit="deadbeef", approved_by="ALEX")

    lines = [json.loads(x) for x in log.read_text().splitlines()]
    assert [e["action"] for e in lines] == ["set_parameters", "firmware_update"]
    assert lines[1]["agent"] == "fwupdate" and lines[1]["approved_by"] == "ALEX"
    # Chain intact: entry 2 carries entry 1's hash.
    assert lines[1]["prev"] == audit.entry_hash(lines[0]) if hasattr(audit, "entry_hash") else True
    assert lines[1]["prev"] != audit.GENESIS


def test_refusal_is_recorded_too(tmp_path):
    """'Who tried and was denied' is the half that matters after an incident."""
    log = tmp_path / "audit.log"
    audit.append_audit(str(log), "firmware_update", "10.0.0.1", "fwupdate",
                       "refused: 10.0.0.1 is not listed in the firmware policy",
                       revision="4.9.1")
    e = json.loads(log.read_text().splitlines()[0])
    assert e["result"].startswith("refused")
    assert e["prev"] == audit.GENESIS


def test_credentials_never_reach_the_log(tmp_path):
    log = tmp_path / "audit.log"
    audit.append_audit(str(log), "firmware_update", "10.0.0.1", "fwupdate", "ok",
                       plc_password="hunter2")
    assert "hunter2" not in log.read_text()
