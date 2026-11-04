# -*- coding: utf-8 -*-
"""Read-only queries against the local Mirantir catalogue (moria.cm3)."""

import sqlite3
import re

MOVIE_CATS = ["Película", "Anime", "Dibujo", "Documental", "Música"]
SERIES_CATS = ["General", "Anime", "Dibujo", "Documental", "Novela", "Reality", "Retro"]
IMG = "https://image.tmdb.org/t/p/"


def _conn(db_path):
    # Plain connection (we only ever read). Avoids file:-URI path issues on
    # Windows/Android, where backslashes and special chars break URI parsing.
    return sqlite3.connect(db_path, timeout=5)


SECTION_CATEGORIES = {
    "movies": (("Película",), ()),
    "shows": ((), ("General", "Retro", "Reality")),
    "soaps": ((), ("Novela",)),
    "cartoons": (("Dibujo",), ("Dibujo",)),
    "anime": (("Anime",), ("Anime",)),
    "music": (("Música",), ()),
    "documentaries": (("Documental", "Ducumental"), ("Documental",)),
}


def list_section(db_path, section, offset=0, limit=60):
    """List a Palantir catalogue section without external menu services."""
    movie_cats, series_cats = SECTION_CATEGORIES[section]
    queries, params = [], []
    columns = ("tmdb,titulo,plot,poster,fondo,genero,fecha,rating,mpaa,"
               "duration,clearlogo,updated")
    if movie_cats:
        marks = ",".join("?" for _ in movie_cats)
        queries.append("SELECT 'movie' media,%s FROM pelis WHERE categoria IN (%s)" %
                       (columns, marks))
        params.extend(movie_cats)
    if series_cats:
        marks = ",".join("?" for _ in series_cats)
        queries.append("SELECT 'series' media,tmdb,titulo,plot,poster,fondo,genero,"
                       "fecha,rating,mpaa,NULL duration,clearlogo,updated FROM series "
                       "WHERE categoria IN (%s)" % marks)
        params.extend(series_cats)
    sql = " UNION ALL ".join(queries) + " ORDER BY updated DESC, tmdb DESC LIMIT ? OFFSET ?"
    params.extend((limit + 1, offset))
    conn = _conn(db_path)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


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
def list_movies(db_path, cat=None, genre=None, search=None, offset=0, limit=60,
                cats=None, year_value=None, sort="updated", letter=None,
                quality_value=None, collection=None):
    where, params = [], []
    if cat:
        where.append("categoria = ?"); params.append(cat)
    elif cats:
        where.append("categoria IN (%s)" % ",".join("?" for _ in cats))
        params.extend(cats)
    if genre:
        where.append("genero LIKE ?"); params.append("%" + genre + "%")
    if year_value:
        where.append("substr(fecha, 1, 4) = ?"); params.append(str(year_value))
    if letter:
        if letter == "0-9":
            where.append("substr(upper(titulo),1,1) between '0' and '9'")
        else:
            where.append("upper(titulo) LIKE ?"); params.append(letter.upper() + "%")
    if quality_value:
        where.append("exists (select 1 from enlaces_pelis ep where ep.tmdb=pelis.tmdb "
                     "and ep.calidad = ?)"); params.append(quality_value)
    if collection:
        where.append("('#' || coalesce(coleccion,'') || '#') LIKE ?")
        params.append("%%#%s#%%" % collection)
    if search:
        where.append("titulo LIKE ? COLLATE NOCASE"); params.append("%" + search + "%")
    sql = ("select tmdb,titulo,plot,poster,fondo,genero,fecha,rating,duration,"
           "mpaa,trailer,clearlogo from pelis")
    if where:
        sql += " WHERE " + " AND ".join(where)
    order = {"title": "titulo COLLATE NOCASE", "date": "fecha DESC, updated DESC",
             "updated": "updated DESC, tmdb DESC"}.get(sort, "updated DESC, tmdb DESC")
    sql += " ORDER BY %s LIMIT ? OFFSET ?" % order
    params += [limit + 1, offset]
    c = _conn(db_path)
    try:
        return c.execute(sql, params).fetchall()
    finally:
        c.close()


def list_series(db_path, cat=None, genre=None, search=None, offset=0, limit=60,
                cats=None, year_value=None, sort="updated", letter=None):
    where, params = [], []
    if cat:
        where.append("categoria = ?"); params.append(cat)
    elif cats:
        where.append("categoria IN (%s)" % ",".join("?" for _ in cats))
        params.extend(cats)
    if genre:
        where.append("genero LIKE ?"); params.append("%" + genre + "%")
    if year_value:
        where.append("substr(fecha, 1, 4) = ?"); params.append(str(year_value))
    if letter:
        if letter == "0-9":
            where.append("substr(upper(titulo),1,1) between '0' and '9'")
        else:
            where.append("upper(titulo) LIKE ?"); params.append(letter.upper() + "%")
    if search:
        where.append("titulo LIKE ? COLLATE NOCASE"); params.append("%" + search + "%")
    sql = ("select tmdb,titulo,plot,poster,fondo,genero,fecha,rating,mpaa from series")
    if where:
        sql += " WHERE " + " AND ".join(where)
    order = {
        "title": "titulo COLLATE NOCASE",
        "date": "fecha DESC, updated DESC",
        "updated": "COALESCE((SELECT MAX(es.updated) FROM enlaces_series es "
                   "WHERE es.tmdb=series.tmdb), updated) DESC, tmdb DESC",
    }.get(sort, "updated DESC, tmdb DESC")
    sql += " ORDER BY %s LIMIT ? OFFSET ?" % order
    params += [limit + 1, offset]
    c = _conn(db_path)
    try:
        return c.execute(sql, params).fetchall()
    finally:
        c.close()


def media_genres(db_path, mtype, cats=None):
    from collections import Counter
    c = _conn(db_path); cnt = Counter()
    try:
        table = "pelis" if mtype == "movie" else "series"
        sql = "select genero from %s where genero is not null" % table
        params = []
        if cats:
            sql += " and categoria in (%s)" % ",".join("?" for _ in cats)
            params.extend(cats)
        for (g,) in c.execute(sql, params):
            for x in g.split("#"):
                x = x.strip()
                if x:
                    cnt[x] += 1
    finally:
        c.close()
    return [g for g, _ in cnt.most_common(30)]


def media_years(db_path, mtype, cats=None):
    table = "pelis" if mtype == "movie" else "series"
    sql = ("select distinct substr(fecha,1,4) year from %s "
           "where fecha is not null and length(fecha) >= 4" % table)
    params = []
    if cats:
        sql += " and categoria in (%s)" % ",".join("?" for _ in cats)
        params.extend(cats)
    sql += " order by year desc"
    c = _conn(db_path)
    try:
        return [row[0] for row in c.execute(sql, params).fetchall() if row[0]]
    finally:
        c.close()


def movie_collections(db_path, specials=False):
    c = _conn(db_path)
    try:
        operator = "=" if specials else ">"
        return c.execute(
            "select id,titulo,poster,fondo from colecciones_pelis "
            "where cast(id as integer) " + operator + " 0 and "
            "exists (select 1 from pelis where "
            "('#' || coalesce(coleccion,'') || '#') like ('%#' || id || '#%')) "
            "order by titulo collate nocase"
        ).fetchall()
    finally:
        c.close()


def movie_qualities(db_path):
    c = _conn(db_path)
    try:
        return [row[0] for row in c.execute(
            "select distinct calidad from enlaces_pelis where calidad is not null "
            "and calidad != '' order by calidad desc").fetchall()]
    finally:
        c.close()


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
