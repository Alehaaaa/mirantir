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

CHECK_INTERVAL = 12 * 60 * 60
PROFILE = xbmcvfs.translatePath(ADDON.getAddonInfo("profile"))
DB_PATH = os.path.join(PROFILE, "moria.cm3")
STATE_PATH = os.path.join(PROFILE, "state.json")


def log(*parts):
    xbmc.log("[Mirantir] " + " ".join(str(part) for part in parts), xbmc.LOGINFO)


def tr(string_id, *values):
    text = ADDON.getLocalizedString(string_id)
    return text.format(*values) if values else text


def last_check():
    return float(source.load_state(STATE_PATH).get("last_check", 0))


def save_last_check(checked_at):
    state = source.load_state(STATE_PATH)
    state["last_check"] = checked_at
    with open(STATE_PATH, "w") as state_file:
        json.dump(state, state_file)


def update_catalogue(show_progress=False):
    """Check quietly; show progress only for a real startup download."""
    if ADDON.getSetting("auto_update") != "true":
        return
    os.makedirs(PROFILE, exist_ok=True)
    info = source.discover()
    if not source.update_required(DB_PATH, STATE_PATH, info):
        save_last_check(time.time())
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
        save_last_check(time.time())
    finally:
        if dialog:
            dialog.close()


def run():
    sync_player(ADDON.getAddonInfo("path"))
    monitor = xbmc.Monitor()
    startup = True
    next_check = last_check() + CHECK_INTERVAL
    if not os.path.isfile(DB_PATH):
        next_check = 0
    while not monitor.abortRequested():
        now = time.time()
        if now >= next_check:
            try:
                update_catalogue(show_progress=startup)
            except Exception as exc:
                log("catalogue update failed:", exc)
            next_check = time.time() + CHECK_INTERVAL
        startup = False
        wait = max(1, min(CHECK_INTERVAL, next_check - time.time()))
        if monitor.waitForAbort(wait):
            break


if __name__ == "__main__":
    run()
