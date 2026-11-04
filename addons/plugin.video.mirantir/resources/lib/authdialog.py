# -*- coding: utf-8 -*-
"""Native Kodi device-code pairing for AllDebrid and RealDebrid."""

import time

import xbmc
import xbmcgui


_ENGLISH_FALLBACK = {
    32069: "Error: {0}",
    32073: "Connect {0}",
    32074: "Visit: {0}",
    32075: "Waiting for confirmation...",
    32076: "New code in {0}s",
    32077: "Connected!",
    32078: "Generating a new code...",
    32079: "Could not generate a code",
    32080: "Could not start the connection",
}


def _tr(addon, string_id, *values):
    text = addon.getLocalizedString(string_id) or _ENGLISH_FALLBACK.get(string_id, "")
    return text.format(*values) if values else text


def _message(addon, flow, seconds, status_id=32075):
    return "[CR]".join((
        _tr(addon, 32074, flow.verify_url),
        "",
        str(flow.code),
        "",
        _tr(addon, 32076, max(0, seconds)),
        _tr(addon, status_id),
    ))


def _save(addon, result):
    for key, value in (result or {}).items():
        addon.setSetting(key, value)


def run_auth(flow, addon, addon_path=None):
    """Pair through Kodi's native progress dialog; returns True on success."""
    dialog = xbmcgui.DialogProgress()
    monitor = xbmc.Monitor()
    try:
        if not flow.start():
            xbmcgui.Dialog().notification("Mirantir", _tr(addon, 32080),
                                          xbmcgui.NOTIFICATION_ERROR)
            return False
        dialog.create(_tr(addon, 32073, flow.name),
                      _message(addon, flow, int(flow.expires_in)))
        while not monitor.abortRequested():
            total = max(30, int(getattr(flow, "expires_in", 600)))
            interval = max(2, int(getattr(flow, "interval", 5)))
            deadline = time.monotonic() + total
            next_poll = 0.0
            while time.monotonic() < deadline and not monitor.abortRequested():
                if dialog.iscanceled():
                    return False
                now = time.monotonic()
                left = max(0, int(deadline - now))
                elapsed = int(100 * (total - left) / total)
                dialog.update(elapsed, _message(addon, flow, left))
                if now >= next_poll:
                    next_poll = now + interval
                    state = flow.poll()
                    if state == "ok":
                        _save(addon, getattr(flow, "result", None))
                        dialog.update(100, _tr(addon, 32077))
                        xbmc.sleep(500)
                        return True
                    if state == "error":
                        break
                if monitor.waitForAbort(0.5):
                    return False
            if dialog.iscanceled() or monitor.abortRequested():
                return False
            dialog.update(100, _tr(addon, 32078))
            if not flow.start():
                xbmcgui.Dialog().notification("Mirantir", _tr(addon, 32079),
                                              xbmcgui.NOTIFICATION_ERROR)
                return False
    except Exception as exc:
        xbmcgui.Dialog().notification("Mirantir", _tr(addon, 32069, exc),
                                      xbmcgui.NOTIFICATION_ERROR)
        return False
    finally:
        dialog.close()
