#!/usr/bin/env python3
"""Live end-to-end Palantir check, intentionally separate from fast unit tests.

Downloads the CURRENT public Palantir release and its actual catalogue once.
Requires external network and disk space; run via GitHub Actions CI smoke job.
"""
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "addons/plugin.video.mirantir/resources/lib"))
import source
import palantir_source as discovery
import catalogue_sync as catalogue
import db


def timed(label, operation):
    start = time.monotonic()
    value = operation()
    duration = time.monotonic() - start
    print("%s: %.2fs" % (label, duration), flush=True)
    return value


def main():
    # Never silently use an explicit test override while checking public
    # source discovery. The release repository is a bootstrap, not the DB.
    for key in ("PALANTIR_DB_REPO", "PALANTIR_ADDON_INDEX_URL",
                "PALANTIR_ADDON_ZIP_URL", "PALANTIR_ADDON_DIR"):
        os.environ.pop(key, None)
    with tempfile.TemporaryDirectory() as folder:
        db_path = str(Path(folder, "moria.cm3"))
        state_path = str(Path(folder, "state.json"))

        info = timed("Resolve current Palantir release and DB source",
                     lambda: source.discover(state_path))
        assert info["repo"] and info["name"].endswith(".zm3"), info
        print("Source:", info["repo"], "snapshot:", info["name"],
              "patches:", len(info.get("patches", [])), flush=True)

        changed, _ = timed("Download, restore, index and validate live SQLite",
                           lambda: source.sync(db_path, state_path, info=info))
        assert changed
        assert not source.update_required(db_path, state_path, info)
        assert os.path.getsize(db_path) > 10_000_000

        for title, op in (
            ("Movies catalogue", lambda: db.list_movies(db_path, limit=5)),
            ("Series catalogue", lambda: db.list_series(db_path, limit=5)),
            ("Home movies section", lambda: db.list_section(db_path, "movies",
                                                             limit=5)),
            ("Home shows section", lambda: db.list_section(db_path, "shows",
                                                            limit=5)),
        ):
            rows = timed(title, op)
            assert rows, title + " unexpectedly empty"

        with sqlite3.connect(db_path) as conn:
            assert conn.execute("PRAGMA quick_check").fetchone()[0] == "ok"
            for table, index in (
                ("pelis", "ix_pelis_cat_upd"),
                ("series", "ix_series_cat_upd"),
                ("enlaces_series", "ix_es_tmdb_upd"),
            ):
                found = {row[1] for row in conn.execute(
                    "PRAGMA index_list('%s')" % table)}
                assert index in found, (table, index, found)

        # Historical encoded data: independent of our synthetic unit-test
        # encoder. This is a real archived .up1, NOT applied to today's DB.
        encoded_url = (
            "https://raw.githubusercontent.com/Maniac2017/Mipal2025/"
            "582da8980fb6/moria_3_3_11.up1"
        )
        sql = timed("Decode real archived Palantir .up1",
                    lambda: catalogue._decode_up(discovery._bytes(encoded_url)))
        assert sql.startswith("INSERT OR REPLACE INTO pelis VALUES("), sql[:120]
        assert len(sql) > 1000, len(sql)

        # Historical plaintext .up2 from early Palantir 3.
        plain_url = (
            "https://raw.githubusercontent.com/Maniac2017/Mipal2025/"
            "2019136a1a/moria_3_3_4.up2"
        )
        plain = timed("Decode real archived plaintext Palantir .up2",
                      lambda: catalogue._decode_up(discovery._bytes(plain_url)))
        assert plain.startswith("INSERT OR REPLACE INTO version"), plain[:120]
        # Apply an ACTUAL archived .up1 to its corresponding historical .zm3,
        # not to today's snapshot (which already incorporates that patch).
        old_base = ("https://raw.githubusercontent.com/Maniac2017/Mipal2025/"
                    "582da8980fb6/")
        historical = {
            "name": "moria_3_3_11.zm3",
            "url": old_base + "moria_3_3_11.zm3",
            "sha": "historical-snapshot-582da8980fb6",
            "repo": "Maniac2017/Mipal2025",
            "commit": "2026-08-08T15:45:55Z",
            "snapshot_date": "2026-08-07T16:08:51",
            "patches": [{
                "name": "moria_3_3_11.up1",
                "url": old_base + "moria_3_3_11.up1",
                "sha": "historical-up1-582da8980fb6",
                "number": 1,
                "date": "2026-08-08T15:45:55",
            }],
        }
        history_db = str(Path(folder, "historical.cm3"))
        history_state = str(Path(folder, "historical.json"))
        changed, details = timed(
            "Historical .zm3 restore followed by real .up1 SQL application",
            lambda: source.sync(history_db, history_state, info=historical))
        assert changed and details["applied_patches"] == [
            "moria_3_3_11.up1"
        ], details
        assert not source.update_required(history_db, history_state, historical)
        with sqlite3.connect(history_db) as conn:
            row = conn.execute(
                "SELECT titulo FROM pelis WHERE tmdb=1368337").fetchone()
            assert row is not None, "historical incremental record missing"
        print("Historical full+incremental migration passed", flush=True)

        print("Live Palantir catalogue smoke test passed", flush=True)


if __name__ == "__main__":
    main()
