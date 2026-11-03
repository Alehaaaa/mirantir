#!/usr/bin/env python3
"""Static release checks for Mirantir's Kodi and TMDb Helper integration."""

from __future__ import annotations

import ast
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADDON = ROOT / "addons" / "plugin.video.mirantir"


def main() -> int:
    metadata = ET.parse(ADDON / "addon.xml").getroot()
    assert metadata.attrib["id"] == "plugin.video.mirantir"
    assert metadata.find("./extension[@point='xbmc.service']") is not None
    player = json.loads((ADDON / "resources/players/mirantir.json").read_text())
    expected = ("play_movie", "play_episode", "search_movie", "search_episode")
    for action in expected:
        value = player[action]
        assert isinstance(value, str), f"{action} must be a string for TMDb Helper 6+"
        assert value.startswith("plugin://plugin.video.mirantir/")
    for source in ADDON.rglob("*.py"):
        ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    print(f"Validated Mirantir {metadata.attrib['version']} and TMDb Helper player schema")
    return 0


if __name__ == "__main__":
    sys.exit(main())
