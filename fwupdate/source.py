"""
Resolve FIRMWARE_SOURCE to a local directory of .wup bundles.

Supported sources - the point is that the *rest* of the pipeline (catalog.py,
fw_update.py) only ever sees a plain directory, so nothing downstream cares
where the bundles came from:

    /firmware                     a mounted directory (local folder, or an SMB/NFS
    file:///mnt/share/fw          share the host has already mounted - mounting is
                                  the OS's job, not this script's)
    s3://bucket/prefix/           an S3 bucket (or any S3-compatible endpoint via
                                  AWS_ENDPOINT_URL); standard AWS credential env
    https://host/path/x.wup       one bundle over HTTPS - this is what a Teams /
                                  SharePoint / OneDrive "anyone with the link"
                                  share URL is, once you append ?download=1
    https://host/path/index.json  a manifest: [{"name","url","sha256"?}, ...] - the
                                  way to serve a whole multi-device bundle set over
                                  HTTPS from anywhere that can host a static file

Downloads are cached by name+size, so re-running does not re-fetch ~200 MB
bundles that are already present.
"""
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path
from urllib.parse import urlparse

import httpx


def _log(msg):
    print(msg, flush=True)


def _http_headers():
    """Bearer token for sources behind auth (SharePoint/Artifactory/etc.)."""
    token = os.environ.get("FIRMWARE_SOURCE_TOKEN", "").strip()
    return {"Authorization": f"Bearer {token}"} if token else {}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _download(url: str, dest: Path, expected_sha256: str | None = None) -> None:
    """Stream one file to dest. Writes to a .part file and renames on success, so
    an interrupted download can never be mistaken for a cached bundle."""
    tmp = dest.with_suffix(dest.suffix + ".part")
    with httpx.stream("GET", url, headers=_http_headers(), follow_redirects=True, timeout=120.0) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in r.iter_bytes(1 << 20):
                f.write(chunk)
    if expected_sha256:
        actual = _sha256(tmp)
        if actual != expected_sha256.lower():
            tmp.unlink(missing_ok=True)
            raise ValueError(f"sha256 mismatch for {dest.name}: expected {expected_sha256}, got {actual}")
    tmp.replace(dest)


def _fetch_https(url: str, cache_dir: Path) -> Path:
    parsed = urlparse(url)
    name = Path(parsed.path).name

    if name.endswith(".wup"):
        dest = cache_dir / name
        if dest.exists():
            _log(f"    cached: {name}")
        else:
            _log(f"    downloading {name}")
            _download(url, dest)
        return cache_dir

    # Anything else is treated as a manifest of bundles.
    r = httpx.get(url, headers=_http_headers(), follow_redirects=True, timeout=60.0)
    r.raise_for_status()
    manifest = r.json()
    entries = manifest["bundles"] if isinstance(manifest, dict) else manifest
    for entry in entries:
        dest = cache_dir / Path(entry["name"]).name  # never trust a remote path
        if dest.exists():
            _log(f"    cached: {dest.name}")
            continue
        _log(f"    downloading {dest.name}")
        _download(entry["url"], dest, entry.get("sha256"))
    return cache_dir


def _fetch_s3(uri: str, cache_dir: Path) -> Path:
    try:
        import boto3  # noqa: PLC0415 - optional dependency, only needed for s3:// sources
    except ImportError:
        raise RuntimeError("s3:// source requires boto3 (pip install boto3)") from None

    parsed = urlparse(uri)
    bucket, prefix = parsed.netloc, parsed.path.lstrip("/")
    s3 = boto3.client("s3", endpoint_url=os.environ.get("AWS_ENDPOINT_URL") or None)

    found = 0
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            if not obj["Key"].endswith(".wup"):
                continue
            found += 1
            dest = cache_dir / Path(obj["Key"]).name
            if dest.exists() and dest.stat().st_size == obj["Size"]:
                _log(f"    cached: {dest.name}")
                continue
            _log(f"    downloading {dest.name} ({obj['Size']} bytes)")
            tmp = dest.with_suffix(dest.suffix + ".part")
            s3.download_file(bucket, obj["Key"], str(tmp))
            tmp.replace(dest)
    if not found:
        raise ValueError(f"no .wup objects under {uri}")
    return cache_dir


def fetch(source: str, cache_dir: str | Path = "/firmware-cache") -> Path:
    """Return a local directory containing .wup bundles for `source`.

    Local directories are returned as-is (never copied). Remote sources are
    synced into cache_dir. Raises ValueError/RuntimeError with a readable
    reason; the caller decides whether that is fatal.
    """
    source = (source or "").strip()
    if not source:
        raise ValueError("FIRMWARE_SOURCE is empty")

    scheme = urlparse(source).scheme

    if scheme in ("", "file"):
        path = Path(urlparse(source).path if scheme == "file" else source)
        if not path.is_dir():
            raise ValueError(f"{path} is not a directory (check the volume mount / share)")
        return path

    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(cache_dir).free < 1 << 30:
        _log(f"    WARNING: less than 1 GB free on {cache_dir} - bundles are ~200 MB each")

    if scheme == "s3":
        return _fetch_s3(source, cache_dir)
    if scheme in ("http", "https"):
        return _fetch_https(source, cache_dir)
    raise ValueError(f"unsupported FIRMWARE_SOURCE scheme {scheme!r} (use a path, file://, s3:// or https://)")


if __name__ == "__main__":
    # Standalone: resolve a source and list what came back.
    src = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("FIRMWARE_SOURCE", "")
    cache = sys.argv[2] if len(sys.argv) > 2 else "/tmp/firmware-cache"
    d = fetch(src, cache)
    print(f"{d}:")
    for p in sorted(d.glob("*.wup")):
        print(f"  {p.name}  {p.stat().st_size} bytes")
