# -*- coding: utf-8 -*-
"""Refresh the Mirantir repository promptly when its checksum changes."""

import os
import time
import urllib.request

import xbmc
import xbmcaddon
import xbmcvfs


ADDON = xbmcaddon.Addon()
PROFILE = xbmcvfs.translatePath(ADDON.getAddonInfo("profile"))
STATE_PATH = os.path.join(PROFILE, "last_checksum")
CHECKSUM_URL = (
    "https://raw.githubusercontent.com/Alehaaaa/mirantir/main/"
    "addons.xml.md5"
)
CHECK_INTERVAL = 300


def log(message):
    xbmc.log("[Mirantir Repository] " + str(message), xbmc.LOGINFO)


def remote_checksum():
    # A unique query avoids GitHub Raw's five-minute shared HTTP cache.
    url = "%s?check=%d" % (CHECKSUM_URL, int(time.time()))
    request = urllib.request.Request(url, headers={"User-Agent": "Kodi Mirantir"})
    with urllib.request.urlopen(request, timeout=15) as response:
        value = response.read(128).decode("ascii", "ignore").strip().lower()
    if len(value) != 32 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError("invalid repository checksum")
    return value


def saved_checksum():
    try:
        with open(STATE_PATH, "r", encoding="ascii") as state_file:
            return state_file.read(64).strip()
    except OSError:
        return ""


def save_checksum(checksum):
    os.makedirs(PROFILE, exist_ok=True)
    with open(STATE_PATH, "w", encoding="ascii") as state_file:
        state_file.write(checksum)


def refresh_if_changed():
    checksum = remote_checksum()
    previous = saved_checksum()
    if checksum == previous:
        return
    log("new metadata detected; refreshing Kodi repositories")
    xbmc.executebuiltin("UpdateAddonRepos")
    save_checksum(checksum)


def run():
    monitor = xbmc.Monitor()
    # Let Kodi finish its normal startup work before the first lightweight check.
    if monitor.waitForAbort(10):
        return
    while not monitor.abortRequested():
        try:
            refresh_if_changed()
        except Exception as exc:
            log("update check failed: %s" % exc)
        if monitor.waitForAbort(CHECK_INTERVAL):
            break


if __name__ == "__main__":
    run()
