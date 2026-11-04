# -*- coding: utf-8 -*-
"""Mirantir — Kodi router.

Native browsing (Movies / Series / Search) from a local SQLite catalogue, plus
TMDBHelper "Players" for Arctic Horizon / Arctic Fuse. Quality filtering (DV/4K
toggles), autoplay-or-chooser, QR debrid pairing, AllDebrid + RealDebrid used as
mutual fallbacks. Self-contained — no external server.
"""

import json
import os
import sys
import urllib.parse

import xbmc
import xbmcgui
import xbmcplugin
import xbmcaddon
import xbmcvfs

import db
import crypto
import debrid
import quality
import source
import tmdb as tmdbapi
import authdialog
import player_integration

ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo("id")
ADDON_PATH = ADDON.getAddonInfo("path")
BASE = sys.argv[0]
HANDLE = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].lstrip("-").isdigit() else -1
PARAMS = dict(urllib.parse.parse_qsl(sys.argv[2][1:])) if len(sys.argv) > 2 else {}

PROFILE = xbmcvfs.translatePath("special://profile/addon_data/%s/" % ADDON_ID)
DB_PATH = os.path.join(PROFILE, "moria.cm3")
STATE_PATH = os.path.join(PROFILE, "state.json")
ADDON_PATH_T = xbmcvfs.translatePath(ADDON_PATH)
WIN = xbmcgui.Window(10000)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _log(*a):
    try:
        xbmc.log("[Mirantir] " + " ".join(str(x) for x in a), xbmc.LOGINFO)
    except Exception:
        pass


def tr(string_id, *values):
    text = ADDON.getLocalizedString(string_id)
    return text.format(*values) if values else text


def _int(v, default=0):
    try:
        return int(v)
    except Exception:
        return default


def _bool(setting, default=False):
    v = ADDON.getSetting(setting)
    if v == "":
        return default
    return v == "true"


def autoplay():
    return _bool("autoplay", False)


def page_size():
    return _int(ADDON.getSetting("page_size") or "60", 60)


def notify(msg, heading="Mirantir", icon=xbmcgui.NOTIFICATION_INFO, ms=4000):
    try:
        xbmcgui.Dialog().notification(heading, msg, icon, ms)
    except Exception:
        pass


def url(**kw):
    return BASE + "?" + urllib.parse.urlencode(kw)


def _fail_resolve():
    if HANDLE > 0:
        try:
            xbmcplugin.setResolvedUrl(HANDLE, False, xbmcgui.ListItem())
        except Exception:
            pass


# --------------------------------------------------------------------------- #
# catalogue download / freshness
# --------------------------------------------------------------------------- #
def _do_sync(force):
    dlg = None
    try:
        dlg = xbmcgui.DialogProgressBG()
        dlg.create("Mirantir", tr(32020))
    except Exception:
        dlg = None

    def prog(got, total):
        try:
            dlg.update(int(got * 100 / total), "Mirantir",
                       tr(32021, got >> 20, total >> 20))
        except Exception:
            pass
    try:
        return source.sync(DB_PATH, STATE_PATH, force=force, progress=prog, log=_log)
    finally:
        try:
            if dlg:
                dlg.close()
        except Exception:
            pass


def ensure_db(force=False):
    try:
        if not os.path.isdir(PROFILE):
            os.makedirs(PROFILE)
    except Exception:
        pass
    have = os.path.isfile(DB_PATH)
    if have and not force:
        # The background service owns scheduled checksum checks. Browsing must
        # never pause for network I/O or briefly flash a progress dialog.
        return True
    try:
        changed, info = _do_sync(force)
        if changed:
            notify(tr(32022, info.get("name", "")))
        return True
    except Exception as e:
        _log("sync error:", e)
        if not os.path.isfile(DB_PATH):
            xbmcgui.Dialog().ok("Mirantir",
                                tr(32023, e))
            return False
        notify(tr(32024),
               icon=xbmcgui.NOTIFICATION_WARNING)
        return True


def check_update():
    """Manual update: download only if the remote hash differs from local.
    Reports via notification only (no popup)."""
    try:
        changed, info = _do_sync(force=False)
    except Exception as e:
        notify(tr(32025, e), icon=xbmcgui.NOTIFICATION_WARNING)
        return
    name = info.get("name", "")
    if changed:
        notify(tr(32022, name))
    else:
        notify(tr(32026, name))


# --------------------------------------------------------------------------- #
# list items
# --------------------------------------------------------------------------- #
def _set_info(li, info):
    try:
        tag = li.getVideoInfoTag()
        tag.setMediaType(info.get("mediatype", "video"))
        if info.get("title"):
            tag.setTitle(info["title"])
        if info.get("tvshowtitle"):
            tag.setTvShowTitle(info["tvshowtitle"])
        if info.get("plot"):
            tag.setPlot(info["plot"])
        if info.get("year"):
            tag.setYear(_int(info["year"]))
        if info.get("genres"):
            tag.setGenres(list(info["genres"]))
        if info.get("rating"):
            tag.setRating(float(info["rating"]))
        if info.get("mpaa"):
            tag.setMpaa(info["mpaa"])
        if info.get("duration"):
            tag.setDuration(_int(info["duration"]))
        if info.get("season") is not None:
            tag.setSeason(_int(info["season"]))
        if info.get("episode") is not None:
            tag.setEpisode(_int(info["episode"]))
        if info.get("aired"):
            tag.setFirstAired(info["aired"])
        return
    except Exception:
        pass
    try:
        d = {"mediatype": info.get("mediatype", "video")}
        for k in ("title", "plot", "mpaa", "aired", "tvshowtitle"):
            if info.get(k):
                d[k] = info[k]
        if info.get("year"):
            d["year"] = _int(info["year"])
        if info.get("genres"):
            d["genre"] = info["genres"]
        if info.get("rating"):
            d["rating"] = float(info["rating"])
        if info.get("duration"):
            d["duration"] = _int(info["duration"])
        if info.get("season") is not None:
            d["season"] = _int(info["season"])
        if info.get("episode") is not None:
            d["episode"] = _int(info["episode"])
        li.setInfo("video", d)
    except Exception:
        pass


def add_dir(label, params, art=None, info=None, playable=False, folder=True):
    li = xbmcgui.ListItem(label=label)
    if art:
        try:
            li.setArt({k: v for k, v in art.items() if v})
        except Exception:
            pass
    if info:
        _set_info(li, info)
    elif label:
        # Folder labels stay plain and skin-neutral. Some skins render Title
        # instead of Label, so provide the same unformatted text in both.
        _set_info(li, {"title": label})
    if playable:
        li.setProperty("IsPlayable", "true")
    try:
        xbmcplugin.addDirectoryItem(HANDLE, url(**params), li, isFolder=folder)
    except Exception as e:
        _log("add_dir error:", e)


# --------------------------------------------------------------------------- #
# navigation
# --------------------------------------------------------------------------- #
def root():
    for section, label_id in (("movies", 32030), ("shows", 32031),
                              ("soaps", 32109), ("cartoons", 32100),
                              ("anime", 32101), ("music", 32102),
                              ("documentaries", 32103)):
        add_dir(tr(label_id),
                {"mode": "section", "section": section})
    add_dir(tr(32032), {"mode": "search", "type": "movie"})
    add_dir(tr(32033), {"mode": "search", "type": "series"})
    add_dir(tr(32012), {"mode": "update"}, folder=False)
    xbmcplugin.endOfDirectory(HANDLE)


def section_listing(section, offset=0):
    limit = page_size()
    rows = db.list_section(DB_PATH, section, offset, limit)
    xbmcplugin.setContent(HANDLE, "videos")
    more = len(rows) > limit
    for row in rows[:limit]:
        mtype = row["media"]
        tmdb = row.get("tmdb")
        art = {"poster": db.img(row.get("poster")),
               "fanart": db.img(row.get("fondo"), "w1280"),
               "thumb": db.img(row.get("poster")),
               "clearlogo": db.img(row.get("clearlogo"))}
        info = {"title": row.get("titulo"), "plot": row.get("plot"),
                "year": db.year(row.get("fecha")),
                "genres": db.genres(row.get("genero")),
                "rating": db.rating(row.get("rating")),
                "mpaa": row.get("mpaa"),
                "mediatype": "movie" if mtype == "movie" else "tvshow"}
        if mtype == "movie":
            info["duration"] = _int(row.get("duration"))
            params = {"mode": "resolve", "type": "movie", "tmdb": tmdb}
            add_dir(row.get("titulo"), params, art=art, info=info,
                    playable=True, folder=False)
        else:
            params = {"mode": "seasons", "tmdb": tmdb,
                      "title": row.get("titulo") or "",
                      "poster": row.get("poster") or "",
                      "fondo": row.get("fondo") or ""}
            add_dir(row.get("titulo"), params, art=art, info=info)
    if more:
        add_dir(tr(32036), {"mode": "section", "section": section,
                "offset": offset + limit})
    xbmcplugin.endOfDirectory(HANDLE)


def cats(mtype):
    add_dir(tr(32034), {"mode": "list", "type": mtype})
    for c in (db.MOVIE_CATS if mtype == "movie" else db.SERIES_CATS):
        add_dir(c, {"mode": "list", "type": mtype, "cat": c})
    add_dir(tr(32035), {"mode": "genres", "type": mtype})
    xbmcplugin.endOfDirectory(HANDLE)


def genres(mtype):
    for g in db.movie_genres(DB_PATH):
        add_dir(g, {"mode": "list", "type": mtype, "genre": g})
    xbmcplugin.endOfDirectory(HANDLE)


def listing(mtype, cat=None, genre=None, search=None, offset=0):
    limit = page_size()
    if mtype == "movie":
        rows = db.list_movies(DB_PATH, cat, genre, search, offset, limit)
    else:
        rows = db.list_series(DB_PATH, cat, genre, search, offset, limit)
    more = len(rows) > limit
    rows = rows[:limit]
    xbmcplugin.setContent(HANDLE, "movies" if mtype == "movie" else "tvshows")
    for r in rows:
        if mtype == "movie":
            (tmdb, titulo, plot, poster, fondo, genero, fecha, rating,
             duration, mpaa, trailer, clearlogo) = r
            art = {"poster": db.img(poster), "fanart": db.img(fondo, "w1280"),
                   "thumb": db.img(poster), "clearlogo": db.img(clearlogo)}
            info = {"title": titulo, "plot": plot, "year": db.year(fecha),
                    "genres": db.genres(genero), "rating": db.rating(rating),
                    "mpaa": mpaa, "duration": _int(duration), "mediatype": "movie"}
            # movie plays directly (chooser/autoplay), no sub-page
            add_dir(titulo, {"mode": "resolve", "type": "movie", "tmdb": tmdb},
                    art=art, info=info, playable=True, folder=False)
        else:
            (tmdb, titulo, plot, poster, fondo, genero, fecha, rating, mpaa) = r
            art = {"poster": db.img(poster), "fanart": db.img(fondo, "w1280"),
                   "thumb": db.img(poster)}
            info = {"title": titulo, "plot": plot, "year": db.year(fecha),
                    "genres": db.genres(genero), "rating": db.rating(rating),
                    "mpaa": mpaa, "mediatype": "tvshow"}
            add_dir(titulo, {"mode": "seasons", "tmdb": tmdb, "title": titulo,
                             "plot": plot or "", "poster": poster or "",
                             "fondo": fondo or ""},
                    art=art, info=info)
    if more:
        nxt = {"mode": "list", "type": mtype, "offset": offset + limit}
        for k in ("cat", "genre", "search"):
            if locals().get(k):
                nxt[k] = locals()[k]
        add_dir(tr(32036), nxt)
    xbmcplugin.endOfDirectory(HANDLE)


def seasons(tmdb, title, poster="", fondo=""):
    xbmcplugin.setContent(HANDLE, "seasons")
    art = {"poster": db.img(poster), "fanart": db.img(fondo, "w1280")}
    for s in db.seasons(DB_PATH, tmdb):
        label = tr(32037) if str(s) == "0" else tr(32038, s)
        add_dir(label, {"mode": "episodes", "tmdb": tmdb, "season": s,
                        "title": title, "poster": poster, "fondo": fondo},
                art=art, info={"title": label, "tvshowtitle": title,
                               "season": s, "mediatype": "season"})
    xbmcplugin.endOfDirectory(HANDLE)


def episodes(tmdb, season, title, poster="", fondo=""):
    xbmcplugin.setContent(HANDLE, "episodes")
    meta = tmdbapi.season_episodes(tmdb, season)   # {} if offline
    show_art = {"fanart": db.img(fondo, "w1280"), "poster": db.img(poster)}
    for e in db.episodes(DB_PATH, tmdb, season):
        m = meta.get(int(e), {})
        name = m.get("name") or tr(32039, e)
        label = "%sx%02d · %s" % (season, int(e), name)
        art = dict(show_art)
        if m.get("still"):
            art["thumb"] = m["still"]
        info = {"title": name, "tvshowtitle": title, "plot": m.get("plot"),
                "season": season, "episode": e, "aired": m.get("aired"),
                "rating": m.get("rating") or None,
                "duration": (m.get("runtime") or 0) * 60, "mediatype": "episode"}
        add_dir(label, {"mode": "resolve", "type": "episode", "tmdb": tmdb,
                        "season": season, "episode": e},
                art=art, info=info, playable=True, folder=False)
    xbmcplugin.endOfDirectory(HANDLE)


# --------------------------------------------------------------------------- #
# playback
# --------------------------------------------------------------------------- #
def _links(mtype, tmdb, season=None, episode=None):
    if mtype == "movie":
        rows = db.movie_links(DB_PATH, tmdb)
    else:
        rows = db.episode_links(DB_PATH, tmdb, season, episode)
    return quality.filter_sort(rows, _bool("enable_dv", False), _bool("enable_4k", True))


def ensure_debrid_or_auth():
    if debrid.configured(ADDON):
        return True
    ch = xbmcgui.Dialog().select(tr(32040), [tr(32005), tr(32007)])
    if ch < 0:
        return False
    return run_auth_service("ad" if ch == 0 else "rd")


def run_auth_service(service):
    ok = authdialog.run_auth(debrid.make_flow(service), ADDON, ADDON_PATH_T)
    if ok:
        notify(tr(32041, "AllDebrid" if service == "ad" else "RealDebrid"))
    return ok and bool(debrid.configured(ADDON))


def _finish_play(direct):
    li = xbmcgui.ListItem(path=direct)
    if HANDLE > 0:
        xbmcplugin.setResolvedUrl(HANDLE, True, li)
    else:
        xbmc.Player().play(direct, li)


def _provider_error_summary(errors):
    """Turn debrid API codes into a concise message suitable for Kodi."""
    translations = {
        "bad_token": 32060,
        "expired": 32060,
        "hoster_unavailable": 32061,
        "hoster_not_free": 32062,
        "unsupported_link": 32063,
        "traffic_exhausted": 32064,
        "permission_denied": 32065,
        "link_host_not_supported": 32062,
        "link_down": 32066,
        "free_trial_limit_reached": 32067,
        "auth_missing_apikey": 32068,
    }
    readable = []
    for combined in errors:
        for entry in combined.split(";"):
            entry = entry.strip()
            if not entry:
                continue
            provider, sep, reason = entry.partition(":")
            provider = {"ad": "AllDebrid", "rd": "RealDebrid"}.get(provider, provider)
            reason = reason.strip()
            string_id = translations.get(reason.lower())
            friendly = tr(string_id) if string_id else reason.replace("_", " ")
            readable.append("%s: %s" % (provider, friendly) if sep else friendly)
    return "; ".join(sorted(set(readable)))


def _play_from(rows):
    """Try sources in order (with provider fallback) until one plays."""
    attempted = min(len(rows), 15)
    decrypted = 0
    provider_errors = []
    dlg = None
    try:
        dlg = xbmcgui.DialogProgressBG()
        dlg.create("Mirantir", tr(32042))
    except Exception:
        dlg = None
    try:
        total = min(len(rows), 15)
        for i, (link, cal, aud, inf) in enumerate(rows[:15], 1):
            try:
                if dlg:
                    dlg.update(int(i * 100 / total), "Mirantir",
                               tr(32043, cal or tr(32044)))
            except Exception:
                pass
            try:
                u = crypto.decrypt_link(link)
            except Exception:
                u = None
            if not u:
                continue
            decrypted += 1
            direct, err, prov = debrid.unlock_any(ADDON, u)
            if direct:
                _finish_play(direct)
                return True
            if err:
                provider_errors.append(str(err))
    finally:
        try:
            if dlg:
                dlg.close()
        except Exception:
            pass
    if decrypted == 0:
        message = tr(32045, attempted)
    elif provider_errors:
        details = _provider_error_summary(provider_errors)
        if len(details) > 110:
            details = details[:107] + "…"
        message = tr(32046, decrypted, attempted, details)
        if "infring" in details.lower():
            message += " " + tr(32047)
    else:
        message = tr(32048, attempted)
    _log("playback failed:", message)
    notify(message, icon=xbmcgui.NOTIFICATION_ERROR, ms=10000)
    return False


def resolve_and_play(mtype, tmdb, season=None, episode=None):
    if tmdb is None or tmdb < 0:
        notify(tr(32049), icon=xbmcgui.NOTIFICATION_WARNING)
        return _fail_resolve()
    try:
        rows = _links(mtype, tmdb, season, episode)
    except Exception as e:
        _log("links error:", e)
        notify(tr(32050, e),
               icon=xbmcgui.NOTIFICATION_ERROR, ms=8000)
        return _fail_resolve()
    if not rows:
        target = tr(32051) if mtype == "movie" else tr(32052, season, episode)
        notify(tr(32053, target),
               icon=xbmcgui.NOTIFICATION_WARNING, ms=8000)
        return _fail_resolve()
    if not ensure_debrid_or_auth():
        notify(tr(32054),
               icon=xbmcgui.NOTIFICATION_WARNING, ms=7000)
        return _fail_resolve()

    if autoplay():
        if not _play_from(rows):
            _fail_resolve()
        return

    # chooser popup
    labels = [quality.label(c, a, i) for (_, c, a, i) in rows]
    idx = xbmcgui.Dialog().select(tr(32055), labels)
    if idx < 0:
        notify(tr(32056),
               icon=xbmcgui.NOTIFICATION_INFO, ms=5000)
        return _fail_resolve()
    ordered = [rows[idx]] + [r for j, r in enumerate(rows) if j != idx]
    if not _play_from(ordered):
        _fail_resolve()


# --------------------------------------------------------------------------- #
# misc
# --------------------------------------------------------------------------- #
def search(mtype):
    media = tr(32030).lower() if mtype == "movie" else tr(32031).lower()
    kb = xbmc.Keyboard("", tr(32057, media))
    kb.doModal()
    if kb.isConfirmed() and kb.getText().strip():
        listing(mtype, search=kb.getText().strip())


def install_player():
    ok, changed, detail = player_integration.sync_player(ADDON_PATH)
    if ok:
        detail = tr(32070 if detail == "updated" else 32071)
        suffix = "\n\n" + tr(32058)
        xbmcgui.Dialog().ok("Mirantir", detail + suffix)
    else:
        if detail == "missing":
            detail = tr(32072)
        xbmcgui.Dialog().ok("Mirantir", tr(32059, detail))


# --------------------------------------------------------------------------- #
# dispatch
# --------------------------------------------------------------------------- #
def run():
    mode = PARAMS.get("mode", "root")
    if mode in ("resolve", "players", "auth", "install_player", "update"):
        if mode in ("resolve", "players") and not os.path.isfile(DB_PATH):
            if not ensure_db():
                return _fail_resolve()
    else:
        if not ensure_db():
            return
    try:
        _dispatch(mode)
    except Exception as e:
        import traceback
        _log("dispatch error:", e, traceback.format_exc())
        notify(tr(32069, e), icon=xbmcgui.NOTIFICATION_ERROR, ms=6000)
        if mode in ("resolve", "players"):
            _fail_resolve()
        elif HANDLE > 0:
            try:
                xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
            except Exception:
                pass


def _dispatch(mode):
    if mode == "root":
        root()
    elif mode == "cats":
        cats(PARAMS["type"])
    elif mode == "section":
        section_listing(PARAMS["section"], _int(PARAMS.get("offset", 0)))
    elif mode == "genres":
        genres(PARAMS["type"])
    elif mode == "list":
        listing(PARAMS["type"], PARAMS.get("cat"), PARAMS.get("genre"),
                PARAMS.get("search"), _int(PARAMS.get("offset", 0)))
    elif mode == "seasons":
        seasons(_int(PARAMS["tmdb"]), PARAMS.get("title", ""),
                PARAMS.get("poster", ""), PARAMS.get("fondo", ""))
    elif mode == "episodes":
        episodes(_int(PARAMS["tmdb"]), _int(PARAMS["season"]), PARAMS.get("title", ""),
                 PARAMS.get("poster", ""), PARAMS.get("fondo", ""))
    elif mode == "resolve":
        resolve_and_play(PARAMS["type"], _int(PARAMS["tmdb"]),
                         _int(PARAMS.get("season")) if PARAMS.get("season") else None,
                         _int(PARAMS.get("episode")) if PARAMS.get("episode") else None)
    elif mode == "players":
        resolve_and_play("movie" if PARAMS.get("media") == "movie" else "episode",
                         _int(PARAMS.get("tmdb"), -1),
                         _int(PARAMS.get("season")) if PARAMS.get("season") else None,
                         _int(PARAMS.get("episode")) if PARAMS.get("episode") else None)
    elif mode == "search":
        search(PARAMS["type"])
    elif mode == "auth":
        run_auth_service(PARAMS.get("service", "ad"))
    elif mode == "install_player":
        install_player()
    elif mode == "update":
        check_update()
    else:
        root()
