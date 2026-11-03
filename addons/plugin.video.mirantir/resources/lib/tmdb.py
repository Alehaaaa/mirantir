# -*- coding: utf-8 -*-
"""Minimal TMDB client — used only to enrich episodes with name/plot/still,
which the local catalogue DB does not store. Key embedded in the addon."""

import json
import urllib.parse
import urllib.request

KEY = "a79d70765e78bc6b322fb6f81bb6659d"
BASE = "https://api.themoviedb.org/3"
IMG = "https://image.tmdb.org/t/p/"
UA = "mirantir/1.0"

_season_cache = {}   # (tmdb, season) -> {episode_number: {...}}


def _get(path, **params):
    params["api_key"] = KEY
    url = BASE + path + "?" + urllib.parse.urlencode(params)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=12) as r:
            return json.load(r)
    except Exception:
        return None


def season_episodes(tmdb, season, lang="es-ES"):
    """Return {episode_number: {name, plot, still, aired, rating, runtime}}."""
    key = (str(tmdb), str(season))
    if key in _season_cache:
        return _season_cache[key]
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
    _season_cache[key] = out
    return out
