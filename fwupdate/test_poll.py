"""ponytail: one runnable check for the failure path.
PLC_IP=1.2.3.4 PLC_PASSWORD=x POLL_INTERVAL=0 python3 test_poll.py"""
import io
import contextlib
import httpx
import fw_update

VALUES = {
    "0-0-firmwareupdate-status": 7,          # Error
    "0-0-firmwareupdate-progress": 61,
    "0-0-firmwareupdate-errorcause": 900,    # SelftestFailed
    "0-0-firmwareupdate-debuginfo": "rauc: slot rootfs.2 self-test returned 1",
    "0-0-firmwareupdate-revertable": True,
}


def handler(request):
    if request.method == "POST":  # getlastlogentries
        return httpx.Response(200, json={"data": {"attributes": {"executionStatus": "done",
                "outArgs": {"Entries": {"value": ["Leave update mode"]}}}}})
    pid = request.url.path.rsplit("/", 1)[-1]
    return httpx.Response(200, json={"data": {"attributes": {"value": VALUES[pid]}}})


out = io.StringIO()
c = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://1.2.3.4")
try:
    with contextlib.redirect_stdout(out):
        fw_update.wait_for_completion(c)
except SystemExit as e:
    assert e.code == 1, e.code
else:
    raise AssertionError("expected the poll loop to bail on status=Error")

text = out.getvalue()
for fragment in ["Error (7)", "SelftestFailed (900)", "self-test returned 1",
                 "revertable: True", "Leave update mode"]:
    assert fragment in text, f"missing {fragment!r} in:\n{text}"
assert "timed out" not in text, "bailed via the timeout path, not the status check"

print("poll failure path: all checks passed")
