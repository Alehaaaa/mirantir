# -*- coding: utf-8 -*-
"""Maintain Mirantir's player integration and local catalogue in the background."""

import json
import os
import sys
import time
from datetime import datetime, timedelta

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
import viewtypes  # noqa: E402

PROFILE = xbmcvfs.translatePath(ADDON.getAddonInfo("profile"))
DB_PATH = os.path.join(PROFILE, "moria.cm3")
STATE_PATH = os.path.join(PROFILE, "state.json")


def log(*parts):
    xbmc.log("[Mirantir] " + " ".join(str(part) for part in parts), xbmc.LOGINFO)


def tr(string_id, *values):
    text = ADDON.getLocalizedString(string_id)
    return text.format(*values) if values else text


def current_check_slot(now=None):
    """Return the current twice-daily slot, for example 2026-11-04-08."""
    now = now or datetime.now()
    if now.hour < 8:
        return (now - timedelta(days=1)).strftime("%Y-%m-%d-20")
    return now.strftime("%Y-%m-%d-20" if now.hour >= 20 else "%Y-%m-%d-08")


def check_due():
    return source.load_state(STATE_PATH).get("check_slot") != current_check_slot()


def mark_checked():
    state = source.load_state(STATE_PATH)
    state["check_slot"] = current_check_slot()
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


def monitor_viewtypes():
    """Persist the selected skin view separately for every page type."""
    monitor = xbmc.Monitor()
    last = (None, None)
    observed_type = None
    settle_until = 0.0
    while not monitor.abortRequested():
        folder = xbmc.getInfoLabel("Container.FolderPath")
        if folder.startswith("plugin://plugin.video.mirantir"):
            page_type = viewtypes.active_page_type()
            if page_type != observed_type:
                observed_type = page_type
                settle_until = time.monotonic() + 1.5
            view_id = viewtypes.current_view_id()
            current = (page_type, view_id)
            if time.monotonic() >= settle_until and view_id and current != last:
                viewtypes.remember(ADDON, page_type, view_id)
                last = current
        else:
            last = (None, None)
            observed_type = None
        if monitor.waitForAbort(0.75):
            break


def run():
    sync_player(ADDON.getAddonInfo("path"))
    if check_due():
        try:
            update_catalogue(show_progress=True)
        except Exception as exc:
            log("catalogue update failed:", exc)
    monitor_viewtypes()


if __name__ == "__main__":
    run()
