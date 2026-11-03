#!/usr/bin/env python3
"""Static release checks for Mirantir's Kodi and TMDb Helper integration."""

from __future__ import annotations

import ast
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADDON = ROOT / "addons" / "plugin.video.mirantir"


def main() -> int:
    metadata = ET.parse(ADDON / "addon.xml").getroot()
    assert metadata.attrib["id"] == "plugin.video.mirantir"
    assert metadata.find("./extension[@point='xbmc.service']") is not None
    assert (ADDON / "icon.png").read_bytes() == (ROOT / "addons/repository.mirantir/icon.png").read_bytes(), \
        "Repository icon must match the Mirantir add-on icon"
    player = json.loads((ADDON / "resources/players/mirantir.json").read_text())
    expected = ("play_movie", "play_episode", "search_movie", "search_episode")
    for action in expected:
        value = player[action]
        assert isinstance(value, str), f"{action} must be a string for TMDb Helper 6+"
        assert value.startswith("plugin://plugin.video.mirantir/")
    for source in ADDON.rglob("*.py"):
        ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    language_root = ADDON / "resources" / "language"
    translations = {}
    for language in ("resource.language.en_gb", "resource.language.es_es",
                     "resource.language.ca_es"):
        po = (language_root / language / "strings.po").read_text(encoding="utf-8")
        translations[language] = {int(value) for value in re.findall(r'msgctxt "#(\d+)"', po)}
        entries = re.findall(r'msgctxt "#(\d+)"\nmsgid "([^"]*)"\nmsgstr "([^"]*)"', po)
        assert len(entries) == len(translations[language]), f"Malformed entries in {language}"
        for string_id, source_text, translated_text in entries:
            assert translated_text, f"Empty translation #{string_id} in {language}"
            source_fields = set(re.findall(r'\{\d+\}', source_text))
            translated_fields = set(re.findall(r'\{\d+\}', translated_text))
            assert source_fields == translated_fields, \
                f"Placeholder mismatch in #{string_id} ({language})"
    assert translations["resource.language.en_gb"] == translations["resource.language.es_es"]
    assert translations["resource.language.en_gb"] == translations["resource.language.ca_es"]
    used_ids = set()
    for source in (ADDON / "resources" / "lib").glob("*.py"):
        source_text = source.read_text()
        used_ids.update(int(value) for value in re.findall(r'\btr\((32\d{3})', source_text))
        used_ids.update(int(value) for value in re.findall(r'_tr\([^,]+,\s*(32\d{3})', source_text))
    settings = ET.parse(ADDON / "resources" / "settings.xml")
    used_ids.update(int(node.attrib["label"]) for node in settings.iter()
                    if node.attrib.get("label", "").isdigit() and int(node.attrib["label"]) >= 32000)
    skin = (ADDON / "resources/skins/Default/1080i/mirantir_auth.xml").read_text()
    used_ids.update(int(value) for value in re.findall(r'\$LOCALIZE\[(32\d{3})\]', skin))
    missing = used_ids - translations["resource.language.en_gb"]
    assert not missing, f"Missing translations for string IDs: {sorted(missing)}"
    print(f"Validated Mirantir {metadata.attrib['version']} and TMDb Helper player schema")
    return 0


if __name__ == "__main__":
    sys.exit(main())
