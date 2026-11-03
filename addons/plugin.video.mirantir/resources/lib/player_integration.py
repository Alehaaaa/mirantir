# -*- coding: utf-8 -*-
"""Install Mirantir's player definition into TMDb Helper safely."""

import os
import shutil

import xbmc
import xbmcvfs

TMDBHELPER_ID = "plugin.video.themoviedb.helper"
PLAYER_DIR = "special://profile/addon_data/%s/players/" % TMDBHELPER_ID
PLAYER_NAME = "mirantir.json"


def sync_player(addon_path):
    """Copy only when needed. Return (success, changed, status/detail)."""
    if not xbmc.getCondVisibility("System.HasAddon(%s)" % TMDBHELPER_ID):
        return False, False, "missing"
    source = os.path.join(xbmcvfs.translatePath(addon_path), "resources", "players",
                          PLAYER_NAME)
    destination_dir = xbmcvfs.translatePath(PLAYER_DIR)
    destination = os.path.join(destination_dir, PLAYER_NAME)
    try:
        if not xbmcvfs.exists(PLAYER_DIR):
            xbmcvfs.mkdirs(PLAYER_DIR)
        with open(source, "rb") as source_file:
            wanted = source_file.read()
        try:
            with open(destination, "rb") as installed_file:
                if installed_file.read() == wanted:
                    return True, False, "current"
        except OSError:
            pass
        shutil.copyfile(source, destination)
        xbmc.log("[Mirantir] TMDb Helper player synchronized", xbmc.LOGINFO)
        return True, True, "updated"
    except Exception as exc:
        xbmc.log("[Mirantir] player synchronization failed: %s" % exc, xbmc.LOGERROR)
        return False, False, str(exc)
