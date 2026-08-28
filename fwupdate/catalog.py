"""
Firmware catalog: maps a device's order number + current version to the
correct .wup bundle for a requested target version.

A catalog entry is built directly from a bundle's own package-info.xml -
never guessed from filenames. See build_catalog.py to (re)generate
catalog.json from a directory of .wup files.
"""
import hashlib
import json
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path


def parse_version(v):
    """'04.09.01' or '4.9.1' -> (4, 9, 1). Tolerant of leading zeros."""
    return tuple(int(p) for p in v.strip().split("."))


def version_in_range(version, range_str):
    """range_str like '3.0.0-4.9.99' (inclusive)."""
    lo, hi = range_str.split("-")
    v = parse_version(version)
    return parse_version(lo) <= v <= parse_version(hi)


def read_bundle_metadata(wup_path: Path):
    """Extract catalog fields from one .wup's package-info.xml, without
    extracting the (large) .raucb payload."""
    with zipfile.ZipFile(wup_path) as zf:
        with zf.open("package-info.xml") as f:
            xml_bytes = f.read()
    root = ET.fromstring(xml_bytes)

    desc = root.find("FirmwareDescription")
    file_el = desc.find("AssociatedFiles/File")
    article_numbers = [a.get("OrderNo") for a in root.findall("ArticleList/Article")]

    group = root.find("GroupList/Group")
    upgrade_el = group.find("Upgrade/VersionList/VersionRange")
    downgrade_el = group.find("Downgrade/VersionList/VersionRange")

    sha256 = hashlib.sha256()
    with open(wup_path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            sha256.update(chunk)

    return {
        "wup_file": wup_path.name,
        "wup_sha256": sha256.hexdigest(),
        "raucb_file": file_el.get("Name"),
        "revision": desc.get("Revision"),
        "release_index": desc.get("ReleaseIndex"),
        "article_numbers": article_numbers,
        "upgrade_range": upgrade_el.get("SoftwareRevision") if upgrade_el is not None else None,
        "downgrade_range": downgrade_el.get("SoftwareRevision") if downgrade_el is not None else None,
    }


def build_catalog(firmware_dir: Path):
    entries = []
    for wup_path in sorted(firmware_dir.glob("*.wup")):
        entries.append(read_bundle_metadata(wup_path))
    return {"bundles": entries}


def load_catalog(catalog_path: Path):
    with open(catalog_path) as f:
        return json.load(f)


def _order_matches(device_order_number, article_numbers):
    """Exact match first (article numbers can carry variant suffixes like
    '0762-5305/8000-0002'); fall back to matching the base order number
    (before any '/') if the device reports it without the suffix."""
    if device_order_number in article_numbers:
        return True
    base = device_order_number.split("/")[0]
    return any(a.split("/")[0] == base for a in article_numbers)


def resolve_bundle(catalog, device_order_number, current_version, target_version=None):
    """Find the bundle for this device. If target_version is given, require
    an exact revision match; otherwise pick the highest-revision compatible
    bundle available ("latest"). Also validates current_version falls in
    the chosen bundle's own upgrade/downgrade range.

    Returns (bundle_dict, direction) where direction is "upgrade" or
    "downgrade", or raises ValueError with a human-readable reason.
    """
    candidates = [b for b in catalog["bundles"] if _order_matches(device_order_number, b["article_numbers"])]
    if not candidates:
        raise ValueError(f"No bundle in catalog lists order number {device_order_number!r}")

    if target_version:
        candidates = [b for b in candidates if b["revision"] == target_version]
        if not candidates:
            raise ValueError(f"No bundle for {device_order_number} at version {target_version!r}")
    else:
        candidates.sort(key=lambda b: parse_version(b["revision"]), reverse=True)

    bundle = candidates[0]
    cur = parse_version(current_version)
    target = parse_version(bundle["revision"])

    if cur == target:
        raise ValueError(f"Device is already at {bundle['revision']} - nothing to do")
    elif target > cur:
        if not version_in_range(current_version, bundle["upgrade_range"]):
            raise ValueError(
                f"Current version {current_version} is outside this bundle's upgrade range "
                f"({bundle['upgrade_range']})"
            )
        return bundle, "upgrade"
    else:
        if not version_in_range(current_version, bundle["downgrade_range"]):
            raise ValueError(
                f"Current version {current_version} is outside this bundle's downgrade range "
                f"({bundle['downgrade_range']})"
            )
        return bundle, "downgrade"
