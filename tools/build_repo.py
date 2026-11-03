#!/usr/bin/env python3
"""Build deterministic Kodi repository metadata and installable ZIP files."""

from __future__ import annotations

import hashlib
import html
import shutil
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADDONS = ROOT / "addons"
ZIPS = ROOT / "zips"
IGNORED_PARTS = {"__pycache__", ".DS_Store"}


def addon_details(addon_dir: Path) -> tuple[str, str, Path]:
    addon_xml = addon_dir / "addon.xml"
    try:
        root = ET.parse(addon_xml).getroot()
    except (ET.ParseError, OSError) as exc:
        raise SystemExit(f"Invalid {addon_xml}: {exc}") from exc
    addon_id = root.get("id")
    version = root.get("version")
    if not addon_id or not version or addon_id != addon_dir.name:
        raise SystemExit(f"Invalid add-on identity in {addon_xml}")
    return addon_id, version, addon_xml


def zip_addon(addon_dir: Path, addon_id: str, version: str) -> Path:
    output_dir = ZIPS / addon_id
    output_dir.mkdir(parents=True, exist_ok=True)
    for old_zip in output_dir.glob(f"{addon_id}-*.zip"):
        old_zip.unlink()
    output = output_dir / f"{addon_id}-{version}.zip"
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for source in sorted(addon_dir.rglob("*")):
            relative_source = source.relative_to(addon_dir)
            ignored = any(part in IGNORED_PARTS for part in relative_source.parts)
            if source.is_file() and not ignored and source.suffix not in {".pyc", ".pyo"}:
                relative = Path(addon_id) / relative_source
                info = zipfile.ZipInfo(str(relative).replace("\\", "/"), (1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                archive.writestr(info, source.read_bytes())
    for asset in ("icon.png", "fanart.jpg"):
        source = addon_dir / asset
        target = output_dir / asset
        if source.exists():
            shutil.copyfile(source, target)
        elif target.exists():
            target.unlink()
    return output


def write_kodi_source_index(packages: list[Path]) -> None:
    for addon_id in ("plugin.video.mirantir", "repository.mirantir"):
        for stale_package in ROOT.glob(f"{addon_id}-*.zip"):
            stale_package.unlink()
    links: list[str] = []
    for package in packages:
        root_package = ROOT / package.name
        shutil.copyfile(package, root_package)
        filename = html.escape(package.name)
        links.append(f'    <li><a href="{filename}">{filename}</a></li>')
    page = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Index of /mirantir/</title>
</head>
<body>
  <h1>Index of /mirantir/</h1>
  <ul>
%s
  </ul>
</body>
</html>
""" % "\n".join(links)
    (ROOT / "index.html").write_text(page, encoding="utf-8")


def main() -> int:
    addon_xml_documents: list[bytes] = []
    packages: list[Path] = []
    ZIPS.mkdir(exist_ok=True)
    addon_icon = ADDONS / "plugin.video.mirantir" / "icon.png"
    repository_icon = ADDONS / "repository.mirantir" / "icon.png"
    if addon_icon.is_file() and repository_icon.parent.is_dir():
        shutil.copyfile(addon_icon, repository_icon)
    addon_dirs = sorted(path for path in ADDONS.iterdir() if path.is_dir())
    if not addon_dirs:
        raise SystemExit("No add-ons found")
    for addon_dir in addon_dirs:
        addon_id, version, addon_xml = addon_details(addon_dir)
        addon_document = addon_xml.read_bytes().strip()
        addon_start = addon_document.find(b"<addon ")
        if addon_start < 0:
            raise SystemExit(f"Missing <addon> root in {addon_xml}")
        addon_xml_documents.append(addon_document[addon_start:])
        packages.append(zip_addon(addon_dir, addon_id, version))
    document = b'<?xml version="1.0" encoding="UTF-8"?>\n<addons>\n' + b"\n".join(addon_xml_documents) + b"\n</addons>\n"
    (ROOT / "addons.xml").write_bytes(document)
    (ROOT / "addons.xml.md5").write_text(hashlib.md5(document).hexdigest(), encoding="ascii")
    write_kodi_source_index(packages)
    print(f"Built {len(addon_dirs)} add-ons")
    return 0


if __name__ == "__main__":
    sys.exit(main())
