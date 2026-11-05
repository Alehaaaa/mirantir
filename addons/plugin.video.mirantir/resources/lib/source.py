# -*- coding: utf-8 -*-
"""Fetch & keep the Mirantir catalogue DB (moria.cm3) up to date, on-device.

Self-contained (stdlib only). Mirrors the addon's own distribution logic:
the DB is published as moria_<ver>.zm3 in a GitHub repo — a ZIP whose 42-byte
local-file header was stripped. We prepend the header, unzip the single
'settings.xml' entry (= the SQLite file), and store it in the addon profile.
The database API is discovered from original Palantir (source.txt or latest
release), with a persisted last-known-good fallback. Full .zm3 snapshots and
Palantir's ordered .upN incremental SQL patches are supported.
"""

import base64
import io
import json
import os
import re
import sqlite3
import shutil
import time
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


def _file_commit_date(api, filename):
    """Palantir compares each file's last Git commit time, not just the repo head."""
    url = api + "/commits?" + urllib.parse.urlencode({
        "path": filename, "page": 1, "per_page": 1})
    commits = _json(url)
    if not commits:
        raise ValueError("no commit date for %s" % filename)
    return commits[0]["commit"]["committer"]["date"][:19]


def _newest(source, preferred_version=None):
    """Enumerate Palantir's full snapshots and incremental .upN patches.

    Keep .full.p4u and .incN.p4u out of this path: Palantir 3.3.11 does
    not consume them, and their encryption/manifest protocol differs.
    """
    api = _api_base(source)
    commit = _json(api + "/commits?page=1&per_page=1")[0]["commit"]["committer"]["date"]
    contents = _json(api + "/contents")
    snapshots, incremental = [], {}
    for item in contents:
        name = item.get("name", "")
        if not item.get("download_url") or not item.get("sha"):
            continue
        snapshot = re.fullmatch(r"moria_(\d+(?:_\d+)*)\.zm3", name)
        patch = re.fullmatch(r"moria_(\d+(?:_\d+)*)\.up(\d+)", name)
        if snapshot:
            ver = tuple(map(int, snapshot.group(1).split("_")))
            snapshots.append((ver, item))
        elif patch:
            ver = tuple(map(int, patch.group(1).split("_")))
            incremental.setdefault(ver, []).append((int(patch.group(2)), item))
    if not snapshots:
        return None
    if preferred_version:
        try:
            expected = tuple(map(int, preferred_version.split(".")))
        except ValueError:
            expected = None
        matches = [entry for entry in snapshots if entry[0] == expected]
        if not matches:
            # Original Palantir processes only files for its own add-on version.
            return None
        version, latest = matches[-1]
    else:
        version, latest = max(snapshots, key=lambda entry: entry[0])
    snapshot_date = _file_commit_date(api, latest["name"])
    patches = []
    for number, item in sorted(incremental.get(version, [])):
        patches.append({
            "name": item["name"], "url": item["download_url"],
            "sha": item["sha"], "number": number,
            "date": _file_commit_date(api, item["name"]),
        })
    return {
        "name": latest["name"], "url": latest["download_url"],
        "sha": latest["sha"], "commit": commit, "repo": source,
        "version": ".".join(map(str, version)),
        "snapshot_date": snapshot_date, "patches": patches,
    }


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
            info = (_newest(source, preferred_version=version) if version
                    else _newest(source))
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


def _retry(operation, path=None):
    """Like Palantir: four tries, with 2/4/8-second backoff."""
    for attempt in range(4):
        try:
            return operation()
        except Exception:
            if path:
                try:
                    os.remove(path)
                except OSError:
                    pass
            if attempt == 3:
                raise
            time.sleep(2 ** (attempt + 1))


def _download_zm3(url, path, progress=None):
    """Stream a reconstructed ZIP; never buffer the 50+ MB archive in RAM."""
    def download():
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=300) as response:
            total = int(response.headers.get("Content-Length", 0))
            got = 0
            with open(path, "wb") as output:
                output.write(ZIP_HEADER)
                while True:
                    chunk = response.read(262144)
                    if not chunk:
                        break
                    output.write(chunk)
                    got += len(chunk)
                    if progress and total:
                        progress(got, total)
            if total and got != total:
                raise IOError("incomplete catalogue download")
    _retry(download, path)


def rebuild_from_file(zm3_path, db_path, build_indexes=True):
    """Extract the original settings.xml SQLite payload to a working file."""
    with zipfile.ZipFile(zm3_path) as archive:
        if "settings.xml" not in archive.namelist():
            raise RuntimeError("Palantir catalogue entry settings.xml is missing")
        tmp = db_path + ".tmp"
        try:
            with archive.open("settings.xml") as src, open(tmp, "wb") as out:
                head = src.read(16)
                if head != b"SQLite format 3\x00":
                    raise RuntimeError("payload is not a SQLite database")
                out.write(head)
                shutil.copyfileobj(src, out, 1024 * 1024)
            if build_indexes:
                _index(tmp)
            os.replace(tmp, db_path)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
    return os.path.getsize(db_path)


def _decode_up(data):
    """Reverse the exact p3b64decode algorithm used for Palantir .upN SQL."""
    value = urllib.parse.unquote_to_bytes(data).replace(b"?", b"").strip()
    padding = (-len(value)) % 4
    quarter = (len(value) + padding) // 4
    encoded = value[:quarter][::-1] + value[quarter:][::-1] + b"=" * padding
    sql = base64.b64decode(encoded, validate=True).decode("utf-8")
    if len(sql.strip()) <= 10:
        raise ValueError("Palantir incremental update has no SQL")
    return sql


def _db_metadata(db_path):
    """An in-database recovery marker avoids replay after state.json loss."""
    if not os.path.isfile(db_path):
        return {}
    try:
        with sqlite3.connect(db_path, timeout=5) as conn:
            row = conn.execute(
                "SELECT value FROM _mirantir_catalogue_state WHERE key='sync'"
            ).fetchone()
            value = json.loads(row[0]) if row else {}
            return value if isinstance(value, dict) else {}
    except (sqlite3.Error, ValueError, TypeError):
        return {}


def _effective_state(db_path, state):
    result = dict(state)
    result.update(_db_metadata(db_path))
    return result


def _plan(db_path, state, info, force=False):
    """Return (rebuild_from_snapshot, pending_patches, desired_patches).

    If a previously applied .upN is replaced, rebuild from the known-good
    snapshot rather than replaying potentially non-idempotent SQL over it.
    """
    state = _effective_state(db_path, state)
    patches = [patch for patch in info.get("patches", [])
               if patch["date"] > info.get("snapshot_date", "")]
    desired = [{"name": p["name"], "sha": p["sha"], "date": p["date"]}
               for p in patches]
    prior = state.get("patches", [])
    if not isinstance(prior, list):
        prior = []
    changed_snapshot = (
        force or not os.path.isfile(db_path)
        or state.get("sha") != info["sha"]
        or (state.get("repo") and state["repo"] != info["repo"])
        or (state.get("name") and state["name"] != info["name"]))
    prefix = (len(prior) <= len(desired) and
              all(p.get("name") == d["name"] and p.get("sha") == d["sha"]
                  for p, d in zip(prior, desired)))
    if changed_snapshot or not prefix:
        return True, patches, desired
    return False, patches[len(prior):], desired


def _write_db_metadata_and_validate(db_path, metadata):
    with sqlite3.connect(db_path, timeout=30) as conn:
        # All SQL changes, including markers, must live in the staged DB.
        conn.execute("PRAGMA journal_mode=DELETE")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS _mirantir_catalogue_state "
            "(key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT OR REPLACE INTO _mirantir_catalogue_state(key,value) "
            "VALUES('sync', ?)", (json.dumps(metadata),))
        conn.commit()
        ok = conn.execute("PRAGMA quick_check").fetchone()
        if not ok or ok[0] != "ok":
            raise RuntimeError("catalogue failed SQLite integrity check")



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
    """Detect a changed snapshot OR any new/modified incremental .upN."""
    rebuild, pending, _ = _plan(db_path, load_state(state_path), info)
    return rebuild or bool(pending)


def sync(db_path, state_path, force=False, progress=None, log=lambda *a: None,
         info=None):
    """Mirror Palantir's full+incremental order, with atomic publication.

    Never modify the live DB in place. A failing patch leaves the prior SQLite
    file and its tracking state untouched; a later check can safely retry.
    """
    info = info or discover(state_path)
    state = load_state(state_path)
    rebuild, pending, desired = _plan(db_path, state, info, force=force)
    if not rebuild and not pending:
        return False, info

    working = db_path + ".building"
    tmp_zm3 = db_path + ".zm3.tmp"
    try:
        if rebuild:
            log("downloading", info["name"], "from", info["repo"])
            _download_zm3(info["url"], tmp_zm3, progress=progress)
            rebuild_from_file(tmp_zm3, working, build_indexes=False)
        else:
            # sqlite readers can safely continue using the original DB.
            shutil.copy2(db_path, working)
        with sqlite3.connect(working, timeout=30) as conn:
            conn.execute("PRAGMA journal_mode=DELETE")
            for patch in pending:
                log("applying", patch["name"], "from", info["repo"])
                payload = _retry(lambda p=patch: _bytes(p["url"]))
                sql = _decode_up(payload)
                # Prevent remote SQL from attaching and writing other files.
                def authorizer(action, arg1, arg2, db_name, trigger):
                    if action in (sqlite3.SQLITE_ATTACH, sqlite3.SQLITE_DETACH):
                        return sqlite3.SQLITE_DENY
                    return sqlite3.SQLITE_OK
                conn.set_authorizer(authorizer)
                try:
                    conn.executescript(sql)
                finally:
                    conn.set_authorizer(None)

        _index(working)
        metadata = {
            "sha": info["sha"], "name": info["name"], "repo": info["repo"],
            "commit": info["commit"], "patches": desired,
        }
        _write_db_metadata_and_validate(working, metadata)
        # Replaces only after all patches and integrity checks succeeded.
        os.replace(working, db_path)
        state.update(metadata)
        _save_state(state_path, state)
        info["bytes"] = os.path.getsize(db_path)
        info["applied_patches"] = [patch["name"] for patch in pending]
        return True, info
    finally:
        for path in (working, working + ".tmp", tmp_zm3):
            try:
                os.remove(path)
            except OSError:
                pass
