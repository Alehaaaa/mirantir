# -*- coding: utf-8 -*-
"""Safely maintain the local catalogue with Palantir's .zm3 and .upN formats.

Downloads and SQL patches are applied to a staging DB; the catalogue is
replaced only after an integrity check, preserving fast offline lookups.
"""

import base64
import json
import os
import re
import shutil
import sqlite3
import time
import urllib.parse
import urllib.request
import zipfile

from palantir_source import UA, _bytes, _save_state, discover, load_state

ZIP_HEADER = base64.b64decode(
    b"UEsDBBQAAAAIAKJchVngR+RlsfTRAQBwSwUMAAAAc2V0dGluZ3MueG1s")


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
    """Decode Palantir p3b64 .upN or legacy plain-SQL .upN packages.

    Some historical .upN files (e.g. 3.3.4.up2) were plain UTF-8 SQL.
    Only unambiguously SQL-looking files take that path; otherwise reverse
    the exact original p3b64decode algorithm.
    """
    raw = urllib.parse.unquote_to_bytes(data).strip()
    plain = raw.lstrip(b"\xef\xbb\xbf \t\r\n")
    if re.match(rb"(?i)(?:INSERT|UPDATE|DELETE|CREATE|ALTER|DROP|REPLACE|BEGIN|WITH)\s", plain):
        return plain.decode("utf-8")
    value = raw.replace(b"?", b"")
    padding = (-len(value)) % 4
    quarter = (len(value) + padding) // 4
    encoded = value[:quarter][::-1] + value[quarter:][::-1] + b"=" * padding
    try:
        sql = base64.b64decode(encoded, validate=True).decode("utf-8")
    except (ValueError, UnicodeError) as exc:
        raise ValueError("invalid Palantir incremental payload") from exc
    if len(sql.strip()) <= 10:
        raise ValueError("Palantir incremental update has no SQL")
    return sql



def _db_metadata(db_path):
    """An in-database recovery marker avoids replay after state.json loss."""
    if not os.path.isfile(db_path):
        return {}
    conn = None
    try:
        conn = sqlite3.connect(db_path, timeout=5)
        row = conn.execute(
            "SELECT value FROM _mirantir_catalogue_state WHERE key='sync'"
        ).fetchone()
        value = json.loads(row[0]) if row else {}
        return value if isinstance(value, dict) else {}
    except (sqlite3.Error, ValueError, TypeError):
        return {}
    finally:
        if conn:
            conn.close()


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
    conn = sqlite3.connect(db_path, timeout=30)
    try:
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
    finally:
        conn.close()



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
        conn = sqlite3.connect(working, timeout=30)
        try:
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
        finally:
            conn.close()

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
