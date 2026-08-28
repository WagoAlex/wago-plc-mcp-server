#!/usr/bin/env python3
"""
Scan a directory of .wup firmware bundles and emit catalog.json.

Usage: build_catalog.py <firmware-dir> [output-path]

Re-run this whenever firmware bundles are added to the directory. The
catalog is derived entirely from each bundle's own package-info.xml -
nothing is inferred from filenames.
"""
import json
import sys
from pathlib import Path

from catalog import build_catalog


def main():
    if len(sys.argv) < 2:
        print(f"usage: {sys.argv[0]} <firmware-dir> [output-path]", file=sys.stderr)
        sys.exit(1)
    firmware_dir = Path(sys.argv[1])
    out_path = Path(sys.argv[2]) if len(sys.argv) > 2 else firmware_dir / "catalog.json"

    catalog = build_catalog(firmware_dir)
    with open(out_path, "w") as f:
        json.dump(catalog, f, indent=2)

    print(f"Wrote {len(catalog['bundles'])} bundle(s) to {out_path}")
    for b in catalog["bundles"]:
        print(f"  {b['wup_file']}: rev={b['revision']} idx={b['release_index']} "
              f"articles={len(b['article_numbers'])} "
              f"upgrade={b['upgrade_range']} downgrade={b['downgrade_range']}")


if __name__ == "__main__":
    main()
