# -*- coding: utf-8 -*-
"""Keep Mirantir's TMDb Helper player definition installed and current."""

import os
import sys

import xbmcaddon

ADDON = xbmcaddon.Addon()
LIB = os.path.join(ADDON.getAddonInfo("path"), "resources", "lib")
if LIB not in sys.path:
    sys.path.insert(0, LIB)

from player_integration import sync_player  # noqa: E402


if __name__ == "__main__":
    sync_player(ADDON.getAddonInfo("path"))
