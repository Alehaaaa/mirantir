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
import urllib.parse
import xml.etree.ElementTree as ET

# This is the Palantir add-on *distribution index*, not a database address.
# It can be overridden without editing Mirantir. No DB repo is hardcoded.
ADDON_REPO_XML = "https://palantir.5g.in/Repo/addons.xml"
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
    """Reverse Palantir's static .md encoding (never execute downloaded code)."""
    n = len(data)
    t = n // 3
    arranged = data[n - t:] + data[:t] + data[t:n - t][::-1]
    return base64.b85decode(arranged).decode("utf-8")


def _normalize_source(value):
    """Accept an original source.txt API base or a GitHub owner/repository."""
    value = (value or "").strip().rstrip("/")
    if re.fullmatch(r"[\w.-]+/[\w.-]+", value):
        return value
    m = re.fullmatch(r"https://github\.com/([\w.-]+/[\w.-]+)", value)
    if m:
        return m.group(1)
    # Original Palantir allows source.txt to contain an alternate API base,
    # so keep an HTTPS API URL rather than assuming every source is GitHub.
    if re.fullmatch(r"https://[^\s?#]+", value):
        return value
    return None


def _api_base(source):
    if source.startswith("https://"):
        return source.rstrip("/")
    return "https://api.github.com/repos/%s" % source


def _original_addon_dir():
    configured = os.environ.get("PALANTIR_ADDON_DIR")
    if configured:
        return configured
    try:
        import xbmcvfs
        return xbmcvfs.translatePath(
            "special://home/addons/plugin.video.palantir3")
    except ImportError:
        return None


def _original_source_override():
    """Mirror Palantir's source.txt priority if the original is installed."""
    folder = _original_addon_dir()
    if not folder:
        return None
    try:
        with open(os.path.join(folder, "source.txt"), encoding="utf-8-sig") as f:
            return _normalize_source(f.read())
    except (OSError, UnicodeError):
        return None


def _repo_from_md(data):
    """Extract the DB API location from original code without importing it."""
    code = _decode_md(data)
    match = re.search(
        r"https://api\.github\.com/repos/([\w.-]+/[\w.-]+)", code)
    if not match:
        raise ValueError("Palantir DB source not found in database module")
    return match.group(1)


def _installed_repo():
    folder = _original_addon_dir()
    if not folder:
        return None
    path = os.path.join(folder, "libs", "ioiiIII11.md")
    try:
        with open(path, "rb") as f:
            return _repo_from_md(f.read())
    except (OSError, ValueError):
        return None


def _derive_repo(state):
    """Read the CURRENT Palantir release, not a historic DB address.

    The index tells us the release version. We only download its large ZIP
    when that version changes; otherwise reuse the source extracted earlier.
    """
    index = os.environ.get("PALANTIR_ADDON_INDEX_URL") or ADDON_REPO_XML
    xml = _bytes(index)
    root = ET.fromstring(xml)
    addon = next((item for item in root.iter("addon")
                  if item.get("id") == ADDON_ID), None)
    if addon is None or not addon.get("version"):
        raise ValueError("Palantir release missing from add-on index")
    version = addon.get("version")
    if (state.get("palantir_index") == index
            and state.get("palantir_version") == version
            and state.get("palantir_repo")):
        return state["palantir_repo"], version, index

    package = ("%s-%s.zip" % (ADDON_ID, version))
    # Kodi repositories normally put ZIPs in <index dir>/<addon id>/<zip>.
    # An override supports indexes with a different ZIP distribution layout.
    template = os.environ.get("PALANTIR_ADDON_ZIP_URL")
    url = (template.format(version=version, addon_id=ADDON_ID)
           if template else urllib.parse.urljoin(
               index, ADDON_ID + "/" + package))
    data = _bytes(url)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        matches = [n for n in zf.namelist()
                   if n.endswith("/libs/ioiiIII11.md")]
        if not matches:
            raise ValueError("Palantir database module missing from ZIP")
        repo = _repo_from_md(zf.read(matches[0]))
    return repo, version, index


def _newest(source):
    api = _api_base(source)
    commit = _json(api + "/commits?page=1&per_page=1")[0]["commit"]["committer"]["date"]
    packages = []
    for item in _json(api + "/contents"):
        name = item.get("name", "")
        match = re.fullmatch(r"moria_(\d+(?:_\d+)*)\.zm3", name)
        if match and item.get("download_url"):
            version = tuple(int(n) for n in match.group(1).split("_"))
            packages.append((version, item))
    if not packages:
        return None
    latest = max(packages, key=lambda item: item[0])[1]
    return {"name": latest["name"], "url": latest["download_url"],
            "sha": latest["sha"], "commit": commit, "repo": source}


def _save_state(state_path, state):
    if not state_path:
        return
    try:
        with open(state_path, "w") as f:
            json.dump(state, f)
    except OSError:
        pass


def discover(state_path=None):
    """Resolve Palantir's authoritative DB source before cached fallbacks.

    Priority: explicit override, original source.txt, current remote Palantir
    module, installed original module, last-known-good source. No hardcoded DB
    repository can silently keep Mirantir on a stale catalogue.
    """
    state = load_state(state_path) if state_path else {}
    providers = [
        ("explicit", lambda: _normalize_source(
            os.environ.get("PALANTIR_DB_REPO"))),
        ("palantir-source.txt", _original_source_override),
        ("current-palantir", lambda: _derive_repo(state)),
        ("installed-palantir", _installed_repo),
        ("cached", lambda: state.get("source_repo") or state.get("repo")),
    ]
    tried = set()
    errors = []
    for kind, resolve in providers:
        try:
            result = resolve()
            if not result:
                continue
            if isinstance(result, tuple):
                source, version, index = result
            else:
                source, version, index = result, None, None
            source = _normalize_source(source)
            if not source or source in tried:
                continue
            tried.add(source)
            info = _newest(source)
            if not info:
                errors.append("%s: no .zm3" % kind)
                continue
            state["source_repo"] = source
            state["source_kind"] = kind
            if version:
                state.update({"palantir_repo": source,
                              "palantir_version": version,
                              "palantir_index": index})
            _save_state(state_path, state)
            return info
        except Exception as exc:
            errors.append("%s: %s" % (kind, exc))
    raise RuntimeError("no Palantir catalogue source available (%s)" %
                       "; ".join(errors[-3:]))


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
    info = info or discover(state_path)
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
