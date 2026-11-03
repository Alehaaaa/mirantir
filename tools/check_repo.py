#!/usr/bin/env python3
"""Validate repository metadata, hashes, and packaged add-ons."""

from __future__ import annotations

import hashlib
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    document = (ROOT / "addons.xml").read_bytes()
    expected = (ROOT / "addons.xml.md5").read_text(encoding="ascii").strip()
    assert hashlib.md5(document).hexdigest() == expected, "addons.xml.md5 is stale"
    root = ET.fromstring(document)
    assert root.tag == "addons"
    for addon in root.findall("addon"):
        addon_id = addon.attrib["id"]
        version = addon.attrib["version"]
        package = ROOT / "zips" / addon_id / f"{addon_id}-{version}.zip"
        assert package.is_file(), f"Missing {package}"
        with zipfile.ZipFile(package) as archive:
            assert archive.testzip() is None, f"Corrupt {package}"
            assert f"{addon_id}/addon.xml" in archive.namelist()
    print(f"Validated {len(root.findall('addon'))} add-ons")
    return 0


if __name__ == "__main__":
    sys.exit(main())
