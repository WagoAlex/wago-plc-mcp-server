"""Firmware source resolution: local dirs pass through, remote sources sync
into a cache, and a corrupted download is never mistaken for a good bundle."""
import functools
import hashlib
import http.server
import json
import threading

import pytest

import source


@pytest.fixture
def served(tmp_path):
    """Serve tmp_path/'remote' over HTTP; yields (base_url, remote_dir)."""
    remote = tmp_path / "remote"
    remote.mkdir()
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(remote))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}", remote
    srv.shutdown()


def test_local_dir_passes_through(tmp_path):
    assert source.fetch(str(tmp_path), tmp_path / "cache") == tmp_path
    assert source.fetch(f"file://{tmp_path}", tmp_path / "cache") == tmp_path


def test_missing_local_dir_refused(tmp_path):
    with pytest.raises(ValueError, match="not a directory"):
        source.fetch(str(tmp_path / "nope"), tmp_path / "cache")


def test_empty_and_unknown_scheme_refused(tmp_path):
    with pytest.raises(ValueError, match="empty"):
        source.fetch("", tmp_path)
    with pytest.raises(ValueError, match="unsupported"):
        source.fetch("ftp://host/fw", tmp_path)


def test_https_single_bundle(served, tmp_path):
    base, remote = served
    (remote / "PFC-G2_update_V040901.wup").write_bytes(b"PK\x03\x04fake")
    cache = tmp_path / "cache"

    got = source.fetch(f"{base}/PFC-G2_update_V040901.wup", cache)
    assert (got / "PFC-G2_update_V040901.wup").read_bytes() == b"PK\x03\x04fake"


def test_https_manifest_verifies_sha256(served, tmp_path):
    base, remote = served
    payload = b"PK\x03\x04bundle"
    (remote / "a.wup").write_bytes(payload)
    (remote / "index.json").write_text(json.dumps([
        {"name": "a.wup", "url": f"{base}/a.wup", "sha256": hashlib.sha256(payload).hexdigest()},
    ]))
    cache = tmp_path / "cache"

    got = source.fetch(f"{base}/index.json", cache)
    assert (got / "a.wup").read_bytes() == payload


def test_https_manifest_rejects_bad_sha256(served, tmp_path):
    base, remote = served
    (remote / "a.wup").write_bytes(b"tampered")
    (remote / "index.json").write_text(json.dumps([
        {"name": "a.wup", "url": f"{base}/a.wup", "sha256": "00" * 32},
    ]))
    cache = tmp_path / "cache"

    with pytest.raises(ValueError, match="sha256 mismatch"):
        source.fetch(f"{base}/index.json", cache)
    assert not (cache / "a.wup").exists()  # a bad download must not linger as a cache hit
