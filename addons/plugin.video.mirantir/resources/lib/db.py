# -*- coding: utf-8 -*-
"""Read-only queries against the local Mirantir catalogue (moria.cm3)."""

import sqlite3

MOVIE_CATS = ["Película", "Anime", "Dibujo", "Documental", "Música"]
SERIES_CATS = ["General", "Anime", "Dibujo", "Documental", "Novela", "Reality", "Retro"]
IMG = "https://image.tmdb.org/t/p/"


def _conn(db_path):
    # Plain connection (we only ever read). Avoids file:-URI path issues on
    # Windows/Android, where backslashes and special chars break URI parsing.
    return sqlite3.connect(db_path, timeout=5)


def img(path, size="w500"):
    if not path:
        return ""
    return path if path.startswith("http") else IMG + size + path


def year(fecha):
    return (fecha or "")[:4]


def rating(r):
    import re
    if not r:
        return None
    m = re.search(r"(\d+(?:\.\d+)?)", r)
    return float(m.group(1)) if m else None


def genres(g):
    return [x.strip() for x in (g or "").split("#") if x.strip()]


# ----------------------------------------------------------------- listings --
def list_movies(db_path, cat=None, genre=None, search=None, offset=0, limit=60):
    where, params = [], []
    if cat:
        where.append("categoria = ?"); params.append(cat)
    if genre:
        where.append("genero LIKE ?"); params.append("%" + genre + "%")
    if search:
        where.append("titulo LIKE ? COLLATE NOCASE"); params.append("%" + search + "%")
    sql = ("select tmdb,titulo,plot,poster,fondo,genero,fecha,rating,duration,"
           "mpaa,trailer,clearlogo from pelis")
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY %s LIMIT ? OFFSET ?" % (
        "titulo COLLATE NOCASE" if search else "updated DESC, tmdb DESC")
    params += [limit + 1, offset]
    c = _conn(db_path)
    try:
        return c.execute(sql, params).fetchall()
    finally:
        c.close()


def list_series(db_path, cat=None, genre=None, search=None, offset=0, limit=60):
    where, params = [], []
    if cat:
        where.append("categoria = ?"); params.append(cat)
    if genre:
        where.append("genero LIKE ?"); params.append("%" + genre + "%")
    if search:
        where.append("titulo LIKE ? COLLATE NOCASE"); params.append("%" + search + "%")
    sql = ("select tmdb,titulo,plot,poster,fondo,genero,fecha,rating,mpaa from series")
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY %s LIMIT ? OFFSET ?" % (
        "titulo COLLATE NOCASE" if search else "updated DESC, tmdb DESC")
    params += [limit + 1, offset]
    c = _conn(db_path)
    try:
        return c.execute(sql, params).fetchall()
    finally:
        c.close()


def movie_genres(db_path):
    from collections import Counter
    c = _conn(db_path); cnt = Counter()
    try:
        for (g,) in c.execute("select genero from pelis where genero is not null"):
            for x in g.split("#"):
                x = x.strip()
                if x:
                    cnt[x] += 1
    finally:
        c.close()
    return [g for g, _ in cnt.most_common(30)]


def seasons(db_path, tmdb):
    c = _conn(db_path)
    try:
        return [r[0] for r in c.execute(
            "select distinct temporada from enlaces_series where tmdb=? "
            "order by temporada", (tmdb,)).fetchall()]
    finally:
        c.close()


def episodes(db_path, tmdb, season):
    c = _conn(db_path)
    try:
        return [r[0] for r in c.execute(
            "select distinct episodio from enlaces_series where tmdb=? and temporada=? "
            "order by episodio", (tmdb, season)).fetchall()]
    finally:
        c.close()


def series_meta(db_path, tmdb):
    c = _conn(db_path)
    try:
        return c.execute(
            "select tmdb,titulo,plot,poster,fondo,genero,fecha,rating,mpaa from series "
            "where tmdb=?", (tmdb,)).fetchone()
    finally:
        c.close()


def movie_links(db_path, tmdb):
    c = _conn(db_path)
    try:
        return c.execute(
            "select link,calidad,audio,info from enlaces_pelis where tmdb=? "
            "order by calidad desc", (tmdb,)).fetchall()
    finally:
        c.close()


def episode_links(db_path, tmdb, season, episode):
    c = _conn(db_path)
    try:
        return c.execute(
            "select link,calidad,audio,info from enlaces_series "
            "where tmdb=? and temporada=? and episodio=? order by calidad desc",
            (tmdb, season, episode)).fetchall()
    finally:
        c.close()
