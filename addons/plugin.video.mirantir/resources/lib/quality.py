# -*- coding: utf-8 -*-
"""Quality parsing / filtering for Mirantir links.

Mirantir serves three main tiers in the `calidad` field:
  * Dolby Vision  -> contains "DV"   (DV, DV HDR10, DV HDR10+, ...)
  * 4K            -> contains "4K"   (4K, 4K HDR10, ...)
  * the rest      -> 1080p / HD / SD
Toggles in settings decide whether DV and 4K are shown.
"""


def is_dv(calidad):
    return "DV" in (calidad or "").upper()


def is_4k(calidad):
    return "4K" in (calidad or "").upper()


def rank(calidad):
    """Higher = better, for 'best source' autoplay and sorting."""
    c = (calidad or "").upper()
    if "DV" in c:
        base = 500
    elif "4K" in c:
        base = 400
    elif "1080" in c:
        base = 300
    elif c.startswith("HD"):
        base = 200
    elif "SD" in c:
        base = 100
    else:
        base = 150
    if "HDR10+" in c:
        base += 30
    elif "HDR10" in c:
        base += 20
    elif "HDR" in c:
        base += 10
    if "IMAX" in c:
        base += 5
    return base


def filter_sort(rows, enable_dv, enable_4k):
    """rows: iterable of (link, calidad, audio, info). Returns filtered + ranked."""
    out = []
    for r in rows:
        c = r[1] or ""
        if is_dv(c) and not enable_dv:
            continue
        if is_4k(c) and not enable_4k:
            continue
        out.append(r)
    # if filtering removed everything (e.g. a title only has DV/4K), fall back
    # to the full set so the user still gets something to play.
    if not out and rows:
        out = list(rows)
    out.sort(key=lambda r: rank(r[1]), reverse=True)
    return out


def label(calidad, audio, info):
    bits = [b for b in (calidad, audio, info) if b]
    return " · ".join(bits) if bits else "1fichier"
