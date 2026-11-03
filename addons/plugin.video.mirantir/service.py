# -*- coding: utf-8 -*-
"""Maintain Mirantir's player integration and local catalogue in the background."""

import json
import os
import sys
import time

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

PROFILE = xbmcvfs.translatePath(ADDON.getAddonInfo("profile"))
DB_PATH = os.path.join(PROFILE, "moria.cm3")
STATE_PATH = os.path.join(PROFILE, "state.json")


def log(*parts):
    xbmc.log("[Mirantir] " + " ".join(str(part) for part in parts), xbmc.LOGINFO)


def tr(string_id, *values):
    text = ADDON.getLocalizedString(string_id)
    return text.format(*values) if values else text


def latest_check_boundary(now=None):
    """Return the latest local 08:00 or 20:00 boundary as a timestamp."""
    now = time.time() if now is None else now
    local = time.localtime(now)
    hour = 20 if local.tm_hour >= 20 else 8
    day = local.tm_mday
    if local.tm_hour < 8:
        day -= 1
        hour = 20
    return time.mktime((local.tm_year, local.tm_mon, day, hour, 0, 0,
                        0, 0, -1))


def check_due():
    state = source.load_state(STATE_PATH)
    return float(state.get("last_check", 0)) < latest_check_boundary()


def mark_checked():
    state = source.load_state(STATE_PATH)
    state["last_check"] = time.time()
    with open(STATE_PATH, "w") as state_file:
        json.dump(state, state_file)


def update_catalogue(show_progress=False):
    """Check quietly; show progress only for a real startup download."""
    if ADDON.getSetting("auto_update") != "true":
        return
    os.makedirs(PROFILE, exist_ok=True)
    info = source.discover()
    if not source.update_required(DB_PATH, STATE_PATH, info):
        mark_checked()
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
        mark_checked()
    finally:
        if dialog:
            dialog.close()


def run():
    sync_player(ADDON.getAddonInfo("path"))
    if check_due():
        try:
            update_catalogue(show_progress=True)
        except Exception as exc:
            log("catalogue update failed:", exc)


if __name__ == "__main__":
    run()
