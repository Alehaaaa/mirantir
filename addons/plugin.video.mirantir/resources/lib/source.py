# -*- coding: utf-8 -*-
"""Fetch & keep the Mirantir catalogue DB (moria.cm3) up to date, on-device.

Self-contained (stdlib only). Mirrors the addon's own distribution logic:
the DB is published as moria_<ver>.zm3 in a GitHub repo — a ZIP whose 42-byte
local-file header was stripped. We prepend the header, unzip the single
'settings.xml' entry (= the SQLite file), and store it in the addon profile.
A self-heal path re-derives the repo from the live addon if the source moves.
"""

import base64
import io
import json
import os
import re
import sqlite3
import urllib.request
import zipfile

DEFAULT_DB_REPO = "Maniac2017/Mipal2025"
ADDON_HOST = "https://palantir.5g.in"
ADDON_REPO_XML = ADDON_HOST + "/Repo/addons.xml"
ADDON_ID = "plugin.video.palantir3"
ZIP_HEADER = base64.b64decode(
    b"UEsDBBQAAAAIAKJchVngR+RlsfTRAQBwSwUMAAAAc2V0dGluZ3MueG1s")
UA = "mirantir/1.0"


def _json(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def _bytes(url, progress=None):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=300) as r:
        total = int(r.headers.get("Content-Length", 0))
        buf, got = io.BytesIO(), 0
        while True:
            chunk = r.read(262144)
            if not chunk:
                break
            buf.write(chunk)
            got += len(chunk)
            if progress and total:
                progress(got, total)
    return buf.getvalue()


def _decode_md(data):
    n = len(data); t = n // 3
    arranged = data[n - t:] + data[:t] + data[t:n - t][::-1]
    return base64.b85decode(arranged).decode("utf-8")


def _derive_repo():
    xml = urllib.request.urlopen(urllib.request.Request(
        ADDON_REPO_XML, headers={"User-Agent": UA}), timeout=60
    ).read().decode("utf-8", "ignore")
    m = re.search(r'id="%s"[^>]*version="([^"]+)"' % re.escape(ADDON_ID), xml)
    ver = m.group(1)
    data = _bytes("%s/Repo/%s/%s-%s.zip" % (ADDON_HOST, ADDON_ID, ADDON_ID, ver))
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        cand = [n for n in zf.namelist() if n.endswith("ioiiIII11.md")]
        md = zf.read(cand[0])
    m = re.search(r'https://api\.github\.com/repos/([\w.\-]+/[\w.\-]+)', _decode_md(md))
    return m.group(1)


def _newest(repo):
    api = "https://api.github.com/repos/%s" % repo
    commit = _json(api + "/commits?page=1&per_page=1")[0]["commit"]["committer"]["date"]
    zips = [c for c in _json(api + "/contents") if c["name"].endswith(".zm3")]
    if not zips:
        return None

    def key(c):
        d = c["name"].replace("moria_", "").split(".zm3")[0]
        return [int(x) for x in d.split("_") if x.isdigit()]
    c = sorted(zips, key=key)[-1]
    return {"name": c["name"], "url": c["download_url"], "sha": c["sha"],
            "commit": commit, "repo": repo}


def discover():
    for repo in (os.environ.get("PALANTIR_DB_REPO"), DEFAULT_DB_REPO):
        if not repo:
            continue
        try:
            info = _newest(repo)
            if info:
                return info
        except Exception:
            pass
    # self-heal
    info = _newest(_derive_repo())
    if not info:
        raise RuntimeError("no catalogue source found")
    return info


def _download_zm3(url, path, progress=None):
    """Stream the .zm3 to disk with the stripped ZIP header prepended, so a
    valid ZIP lands on disk without buffering it all in RAM."""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=300) as r:
        total = int(r.headers.get("Content-Length", 0))
        got = 0
        with open(path, "wb") as f:
            f.write(ZIP_HEADER)
            while True:
                chunk = r.read(262144)
                if not chunk:
                    break
                f.write(chunk)
                got += len(chunk)
                if progress and total:
                    progress(got, total)


def rebuild_from_file(zm3_path, db_path):
    """Extract the single SQLite entry from the (reconstructed) ZIP on disk,
    decompressing in chunks to keep memory low on constrained devices."""
    import shutil
    with zipfile.ZipFile(zm3_path) as zf:
        name = zf.namelist()[0]
        tmp = db_path + ".tmp"
        with zf.open(name) as src, open(tmp, "wb") as out:
            head = src.read(16)
            if head[:16] != b"SQLite format 3\x00":
                raise RuntimeError("payload is not a SQLite DB")
            out.write(head)
            shutil.copyfileobj(src, out, 1024 * 1024)
    _index(tmp)
    os.replace(tmp, db_path)
    return os.path.getsize(db_path)


def _index(db_path):
    conn = sqlite3.connect(db_path)
    try:
        for s in (
            "CREATE INDEX IF NOT EXISTS ix_pelis_cat ON pelis(categoria)",
            "CREATE INDEX IF NOT EXISTS ix_pelis_upd ON pelis(updated)",
            "CREATE INDEX IF NOT EXISTS ix_series_cat ON series(categoria)",
            "CREATE INDEX IF NOT EXISTS ix_ep_tmdb ON enlaces_pelis(tmdb)",
            "CREATE INDEX IF NOT EXISTS ix_es_tmdb ON enlaces_series(tmdb,temporada,episodio)",
        ):
            conn.execute(s)
        conn.commit()
    finally:
        conn.close()


def load_state(state_path):
    try:
        with open(state_path) as f:
            return json.load(f)
    except Exception:
        return {}


def update_required(db_path, state_path, info):
    """Return whether the local catalogue differs from the remote checksum."""
    return not (os.path.isfile(db_path)
                and load_state(state_path).get("sha") == info["sha"])


def sync(db_path, state_path, force=False, progress=None, log=lambda *a: None,
         info=None):
    """Return (changed, info). Downloads only when the .zm3 sha changed."""
    state = load_state(state_path)
    info = info or discover()
    if (not force and os.path.isfile(db_path)
            and state.get("sha") == info["sha"]):
        return False, info
    log("downloading", info["name"], "from", info["repo"])
    tmp_zm3 = db_path + ".zm3.tmp"
    try:
        _download_zm3(info["url"], tmp_zm3, progress=progress)
        size = rebuild_from_file(tmp_zm3, db_path)
    finally:
        try:
            os.remove(tmp_zm3)
        except Exception:
            pass
    info["bytes"] = size
    state.update({"sha": info["sha"], "name": info["name"], "repo": info["repo"],
                  "commit": info["commit"]})
    try:
        with open(state_path, "w") as f:
            json.dump(state, f)
    except Exception:
        pass
    return True, info
