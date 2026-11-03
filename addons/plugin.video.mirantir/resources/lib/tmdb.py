# -*- coding: utf-8 -*-
"""Episode metadata for the catalogue (names/plots/stills the local DB lacks).

If the TMDBHelper add-on (plugin.video.themoviedb.helper) is installed, we use
it — via JSON-RPC Files.GetDirectory — so episodes inherit TMDBHelper's own API
key, language and cache. Otherwise we fall back to a minimal direct TMDB client.
"""

import json
import urllib.parse
import urllib.request

KEY = "a79d70765e78bc6b322fb6f81bb6659d"
BASE = "https://api.themoviedb.org/3"
IMG = "https://image.tmdb.org/t/p/"
UA = "mirantir/1.0"
TMDBHELPER_ID = "plugin.video.themoviedb.helper"

_season_cache = {}   # (tmdb, season) -> {episode_number: {...}}


# --------------------------------------------------------------------------- #
# TMDBHelper path (preferred when installed)
# --------------------------------------------------------------------------- #
def _tmdbhelper_available():
    try:
        import xbmc
        return bool(xbmc.getCondVisibility("System.HasAddon(%s)" % TMDBHELPER_ID))
    except Exception:
        return False


def _via_tmdbhelper(tmdb, season):
    """Ask TMDBHelper to build the episode list and read it back via JSON-RPC."""
    try:
        import xbmc
        path = ("plugin://%s/?info=episodes&type=tv&tmdb_id=%s&season=%s"
                % (TMDBHELPER_ID, tmdb, season))
        req = {
            "jsonrpc": "2.0", "id": 1, "method": "Files.GetDirectory",
            "params": {
                "directory": path, "media": "video",
                "properties": ["title", "plot", "art", "season", "episode",
                               "firstaired", "rating", "runtime", "duration"],
            },
        }
        res = json.loads(xbmc.executeJSONRPC(json.dumps(req)))
        files = (res.get("result") or {}).get("files") or []
        out = {}
        for it in files:
            ep = it.get("episode")
            if ep is None or int(ep) < 0:
                continue
            art = it.get("art") or {}
            secs = it.get("runtime") or it.get("duration") or 0
            out[int(ep)] = {
                "name": it.get("title") or it.get("label") or "",
                "plot": it.get("plot") or "",
                "still": art.get("thumb") or art.get("poster") or "",
                "aired": it.get("firstaired") or "",
                "rating": it.get("rating") or 0,
                "runtime": (int(secs) // 60) if secs else 0,   # -> minutes
            }
        return out
    except Exception:
        return {}


# --------------------------------------------------------------------------- #
# direct TMDB fallback
# --------------------------------------------------------------------------- #
def _get(path, **params):
    params["api_key"] = KEY
    url = BASE + path + "?" + urllib.parse.urlencode(params)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=12) as r:
            return json.load(r)
    except Exception:
        return None


def _via_tmdb_api(tmdb, season, lang):
    out = {}
    d = _get("/tv/%s/season/%s" % (tmdb, season), language=lang)
    if d and isinstance(d.get("episodes"), list):
        for e in d["episodes"]:
            num = e.get("episode_number")
            if num is None:
                continue
            still = e.get("still_path")
            out[int(num)] = {
                "name": e.get("name") or "",
                "plot": e.get("overview") or "",
                "still": (IMG + "w780" + still) if still else "",
                "aired": e.get("air_date") or "",
                "rating": e.get("vote_average") or 0,
                "runtime": e.get("runtime") or 0,
            }
    return out


# --------------------------------------------------------------------------- #
# public
# --------------------------------------------------------------------------- #
def season_episodes(tmdb, season, lang="es-ES"):
    """Return {episode_number: {name, plot, still, aired, rating, runtime}}.
    Prefers TMDBHelper when installed; falls back to the direct TMDB client."""
    key = (str(tmdb), str(season))
    if key in _season_cache:
        return _season_cache[key]
    out = {}
    if _tmdbhelper_available():
        out = _via_tmdbhelper(tmdb, season)
    if not out:
        out = _via_tmdb_api(tmdb, season, lang)
    _season_cache[key] = out
    return out
