# -*- coding: utf-8 -*-
"""Maintain Mirantir's player integration and local catalogue in the background."""

import os
import sys

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

ADDON = xbmcaddon.Addon()
LIB = os.path.join(ADDON.getAddonInfo("path"), "resources", "lib")
if LIB not in sys.path:
    sys.path.insert(0, LIB)

from player_integration import sync_player  # noqa: E402
import source  # noqa: E402

CHECK_INTERVAL = 12 * 60 * 60
PROFILE = xbmcvfs.translatePath(ADDON.getAddonInfo("profile"))
DB_PATH = os.path.join(PROFILE, "moria.cm3")
STATE_PATH = os.path.join(PROFILE, "state.json")


def log(*parts):
    xbmc.log("[Mirantir] " + " ".join(str(part) for part in parts), xbmc.LOGINFO)


def tr(string_id, *values):
    text = ADDON.getLocalizedString(string_id)
    return text.format(*values) if values else text


def update_catalogue(show_progress=False):
    """Check quietly; show progress only for a real startup download."""
    if ADDON.getSetting("auto_update") != "true":
        return
    os.makedirs(PROFILE, exist_ok=True)
    info = source.discover()
    if not source.update_required(DB_PATH, STATE_PATH, info):
        return

    dialog = None
    if show_progress:
        dialog = xbmcgui.DialogProgressBG()
        dialog.create("Mirantir", tr(32020))

    def progress(got, total):
        if dialog and total:
            dialog.update(int(got * 100 / total), "Mirantir",
                          tr(32021, got >> 20, total >> 20))

    try:
        source.sync(DB_PATH, STATE_PATH, progress=progress, log=log, info=info)
    finally:
        if dialog:
            dialog.close()


def run():
    sync_player(ADDON.getAddonInfo("path"))
    monitor = xbmc.Monitor()
    startup = True
    while not monitor.abortRequested():
        try:
            update_catalogue(show_progress=startup)
        except Exception as exc:
            log("catalogue update failed:", exc)
        startup = False
        if monitor.waitForAbort(CHECK_INTERVAL):
            break


if __name__ == "__main__":
    run()
