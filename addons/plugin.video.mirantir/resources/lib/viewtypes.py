# -*- coding: utf-8 -*-
"""Remember one Kodi view control for each kind of Mirantir page."""

import json
import os

import xbmc
import xbmcgui
import xbmcvfs


PROPERTY = "Mirantir.ViewType"
PAGE_TYPES = ("menus", "movies", "tvshows", "mixed", "seasons", "episodes")


def _path(addon):
    profile = xbmcvfs.translatePath(addon.getAddonInfo("profile"))
    return profile, os.path.join(profile, "views.json")


def _load(addon):
    try:
        with open(_path(addon)[1], "r", encoding="utf-8") as view_file:
            value = json.load(view_file)
            return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def current_view_id():
    try:
        value = int(xbmc.getInfoLabel("System.CurrentControlID"))
    except (TypeError, ValueError):
        return 0
    # Kodi content containers normally use 50-59 or 500-series IDs. Keeping
    # this bounded avoids recording side-menu and dialog controls as views.
    return value if 50 <= value <= 899 else 0


def remember(addon, page_type, view_id=None):
    if page_type not in PAGE_TYPES:
        return False
    view_id = view_id or current_view_id()
    if not view_id:
        return False
    profile, path = _path(addon)
    views = _load(addon)
    if views.get(page_type) == view_id:
        return False
    views[page_type] = view_id
    try:
        os.makedirs(profile, exist_ok=True)
        temporary = path + ".tmp"
        with open(temporary, "w", encoding="utf-8") as view_file:
            json.dump(views, view_file, sort_keys=True)
        os.replace(temporary, path)
        return True
    except Exception:
        return False


def activate(addon, page_type):
    if page_type not in PAGE_TYPES:
        return
    xbmcgui.Window(10000).setProperty(PROPERTY, page_type)
    try:
        view_id = int(_load(addon).get(page_type, 0))
    except (TypeError, ValueError):
        view_id = 0
    if view_id:
        xbmc.executebuiltin("Container.SetViewMode(%d)" % view_id)


def active_page_type():
    return xbmcgui.Window(10000).getProperty(PROPERTY)
