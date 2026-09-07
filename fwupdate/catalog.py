"""
Firmware catalog: maps a device's order number + current version to the
correct .wup bundle for a requested target version.

A catalog entry is built directly from a bundle's own package-info.xml -
never guessed from filenames. See build_catalog.py to (re)generate
catalog.json from a directory of .wup files.
"""
import json
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path


# Minimum firmware build a device must already run before it may be updated,
# by base order number. Below this the update path is not supported and the
# device needs an intermediate step first - the bundle's own declared version
# range does not express this, because it is a per-hardware constraint rather
# than a property of the image.
#
# Stated by the fleet owner, 2026-09-07: build 28 for CC100, PFC200 G2, TP600
# and Edge Controller; build 30 for PFC300.
DEFAULT_MINIMUM_BUILD = 28
MINIMUM_BUILD = {
    "0750-8302": 30,  # PFC300
}

# 0750-8217 (PFC200 G2 with modem) takes the red-autoupdate line, which carries
# the modem firmware. Both PFC-G2 bundles list all 35 article numbers including
# this one, so the bundles themselves cannot disambiguate - only the approved
# revision can. Kept here to make the refusal message say something useful.
MODEM_VARIANT_ORDER = "0750-8217"
MODEM_VARIANT_REVISION = "4.9.50"


def minimum_build_for(device_order_number):
    """The build this hardware must already be at to be updated."""
    base = device_order_number.split("/")[0]
    return MINIMUM_BUILD.get(base, DEFAULT_MINIMUM_BUILD)


def check_minimum_build(device_order_number, current_build):
    """Raise ValueError when the device is too old to take this update path.

    current_build is 0-0-version-softwarereleaseindex, the NN in 04.09.01(31).
    """
    minimum = minimum_build_for(device_order_number)
    try:
        build = int(str(current_build).strip())
    except (TypeError, ValueError):
        raise ValueError(
            f"cannot read the device's firmware build ({current_build!r}); "
            f"{device_order_number} requires build >= {minimum} before updating"
        ) from None
    if build < minimum:
        raise ValueError(
            f"{device_order_number} is at build {build}, below the minimum {minimum} "
            f"for this update path. Update it to build {minimum} first."
        )
    return build


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

    return {
        "wup_file": wup_path.name,
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


def resolve_bundle(catalog, device_order_number, current_version, target_version=None, allow_reflash=False):
    """Find the bundle for this device. If target_version is given, require
    an exact revision match; otherwise require that exactly one bundle
    lists this order number. Also validates current_version falls in the
    chosen bundle's own upgrade/downgrade range.

    Returns (bundle_dict, direction) where direction is "upgrade",
    "downgrade" or "reflash", or raises ValueError with a human-readable
    reason. allow_reflash permits writing the version a device already runs -
    normally refused as pointless, but it is the only way to re-seat a slot or
    to prove the pipeline end-to-end on an already-current fleet.
    """
    candidates = [b for b in catalog["bundles"] if _order_matches(device_order_number, b["article_numbers"])]
    if not candidates:
        raise ValueError(f"No bundle in catalog lists order number {device_order_number!r}")

    if target_version:
        candidates = [b for b in candidates if b["revision"] == target_version]
        if not candidates:
            raise ValueError(f"No bundle for {device_order_number} at version {target_version!r}")
    elif len(candidates) > 1:
        # Refuse rather than guess. Nothing in package-info.xml distinguishes a
        # variant line from the standard one: both PFC-G2 bundles list the same
        # 35 article numbers, and red-autoupdate carries a *higher* revision
        # (4.9.50 vs 4.9.1). "Highest revision wins" would put the 0750-8217
        # modem line onto every other PFC200 G2.
        listing = ", ".join(f"{b['revision']} ({b['wup_file']})" for b in candidates)
        hint = ""
        if device_order_number.split("/")[0] == MODEM_VARIANT_ORDER:
            hint = (f" This is the {MODEM_VARIANT_ORDER} modem variant, which takes "
                    f"{MODEM_VARIANT_REVISION} (red-autoupdate, modem firmware included).")
        raise ValueError(
            f"{len(candidates)} bundles match order number {device_order_number}: {listing}. "
            f"Set TARGET_VERSION to the revision you want.{hint}"
        )

    bundle = candidates[0]
    cur = parse_version(current_version)
    target = parse_version(bundle["revision"])

    if cur == target:
        if not allow_reflash:
            raise ValueError(
                f"Device is already at {bundle['revision']} - nothing to do "
                f"(set FW_ALLOW_REFLASH=true to write it anyway)"
            )
        if not version_in_range(current_version, bundle["upgrade_range"]):
            raise ValueError(
                f"Current version {current_version} is outside this bundle's upgrade range "
                f"({bundle['upgrade_range']})"
            )
        return bundle, "reflash"
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
