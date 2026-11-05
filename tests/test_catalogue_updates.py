"""Palantir 3.3.11 catalogue update protocol: .zm3 plus numbered .up SQL.

No network and no Kodi installation required.
"""
import base64
import io
import json
import os
from pathlib import Path
from contextlib import closing
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "addons"
                       / "plugin.video.mirantir" / "resources" / "lib"))
import source
import palantir_source as discovery
import catalogue_sync as catalogue


def p3encode(sql):
    """Original Palantir p3b64encode, independent of Mirantir's decoder."""
    value = base64.b64encode(sql.encode("utf-8"))
    quarter = len(value) // 4
    value = value.replace(b"=", b"")
    return value[:quarter][::-1] + value[quarter:][::-1]


def make_db(path):
    with closing(sqlite3.connect(path)) as conn:
        conn.executescript("""
            CREATE TABLE pelis (tmdb INTEGER PRIMARY KEY, categoria TEXT, updated TEXT);
            CREATE TABLE series (tmdb INTEGER PRIMARY KEY, categoria TEXT, updated TEXT);
            CREATE TABLE enlaces_pelis (tmdb INTEGER);
            CREATE TABLE enlaces_series (tmdb INTEGER, temporada INTEGER, episodio INTEGER, updated TEXT);
            INSERT INTO pelis VALUES (1, 'Película', '2026-11-01');
        """)


def remote_info(patches=None, sha="full-1"):
    return {
        "name": "moria_3_3_11.zm3", "url": "https://example.com/full.zm3",
        "sha": sha, "repo": "Example/Catalogue", "commit": "2026-11-04T20:00:00Z",
        "version": "3.3.11", "snapshot_date": "2026-11-01T10:00:00",
        "patches": patches or [],
    }


def patch(number, sha, date="2026-11-02T10:00:00"):
    return {"name": "moria_3_3_11.up%d" % number,
            "number": number, "sha": sha, "date": date,
            "url": "https://example.com/up%d" % number}


def rows(path):
    with closing(sqlite3.connect(path)) as conn:
        return conn.execute("SELECT tmdb FROM pelis ORDER BY tmdb").fetchall()


class CatalogueUpdateTests(unittest.TestCase):
    def test_decodes_palantir_p3b64_with_padding_and_accents(self):
        for sql in (
            "INSERT INTO pelis VALUES (2, 'Película', '2026-11-02');",
            "UPDATE pelis SET categoria='Español' WHERE tmdb=1;",
            "CREATE INDEX IF NOT EXISTS ix_foo ON pelis(tmdb);",
        ):
            self.assertEqual(catalogue._decode_up(p3encode(sql)), sql)
        with self.assertRaises(ValueError):
            catalogue._decode_up(b"broken")

    def test_newest_filters_p4u_and_tracks_incremental_commits(self):
        contents = [
            {"name": "moria_3_3_11.zm3", "sha": "snap", "download_url": "https://full"},
            {"name": "moria_3_3_11.up2", "sha": "two", "download_url": "https://up2"},
            {"name": "moria_3_3_11.up1", "sha": "one", "download_url": "https://up1"},
            {"name": "moria_3_3_11.full.p4u", "sha": "p4u", "download_url": "https://p4u"},
            {"name": "moria_3_3_11.inc1.p4u", "sha": "inc", "download_url": "https://inc"},
            {"name": "manifest.json", "sha": "json", "download_url": "https://manifest"},
            {"name": "moria_3_3_10.zm3", "sha": "old", "download_url": "https://old"},
        ]
        commits = [{"commit": {"committer": {"date": "2026-11-04T12:00:00Z"}}}]
        with mock.patch.object(source, "_json", side_effect=[commits, contents]), \
                mock.patch.object(source, "_file_commit_date",
                                  side_effect=["2026-11-01T08:00:00",
                                               "2026-11-02T09:00:00",
                                               "2026-11-03T09:00:00"]) as dates:
            data = discovery._newest("Owner/DB", preferred_version="3.3.11")
        self.assertEqual(data["version"], "3.3.11")
        self.assertEqual(data["sha"], "snap")
        self.assertEqual([p["name"] for p in data["patches"]],
                         ["moria_3_3_11.up1", "moria_3_3_11.up2"])
        self.assertEqual(dates.call_count, 3)
        with mock.patch.object(source, "_json", side_effect=[commits, contents]):
            self.assertIsNone(discovery._newest("Owner/DB", preferred_version="3.3.12"))

    def test_reconstructs_stripped_header_zm3_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            source_db = str(Path(tmp, "source.sqlite"))
            make_db(source_db)
            content = Path(source_db).read_bytes()
            archive = io.BytesIO()
            with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("settings.xml", content)
            compressed = archive.getvalue()
            # Palantir strips exactly the 42-byte local ZIP entry header.
            self.assertEqual(compressed[:4], b"PK\x03\x04")
            self.assertEqual(len(source.ZIP_HEADER), 42)
            zm3 = Path(tmp, "file.zm3")
            zm3.write_bytes(source.ZIP_HEADER + compressed[42:])
            dest = str(Path(tmp, "restored.sqlite"))
            self.assertEqual(source.rebuild_from_file(str(zm3), dest),
                             os.stat(dest).st_size)
            self.assertEqual(rows(dest), [(1,)])

    def test_snapshot_then_incremental_only_check_then_in_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            db, state = str(Path(tmp, "db.sqlite")), str(Path(tmp, "state.json"))
            full = remote_info()
            added = p3encode(
                "INSERT INTO pelis VALUES (2, 'Película', '2026-11-02');")
            added2 = p3encode(
                "INSERT INTO pelis VALUES (3, 'Película', '2026-11-03');")
            def fake_rebuild(_archive, path, build_indexes=True):
                make_db(path)
                return os.path.getsize(path)
            with mock.patch.object(source, "_download_zm3"), \
                    mock.patch.object(source, "rebuild_from_file",
                                      side_effect=fake_rebuild), \
                    mock.patch.object(source, "_bytes",
                                      side_effect=[added, added2]) as fetch:
                changed, _ = source.sync(db, state, info=full)
                self.assertTrue(changed)
                self.assertEqual(rows(db), [(1,)])
                self.assertFalse(source.update_required(db, state, full))
                first_patch = remote_info([patch(1, "patch-one")])
                self.assertTrue(source.update_required(db, state, first_patch))
                changed, result = source.sync(db, state, info=first_patch)
                self.assertTrue(changed)
                self.assertEqual(result["applied_patches"],
                                 ["moria_3_3_11.up1"])
                self.assertEqual(rows(db), [(1,), (2,)])
                self.assertFalse(source.update_required(db, state, first_patch))
                second_patch = remote_info([patch(1, "patch-one"),
                                            patch(2, "patch-two",
                                                  "2026-11-03T09:00:00")])
                self.assertTrue(source.update_required(db, state, second_patch))
                changed, result = source.sync(db, state, info=second_patch)
                self.assertTrue(changed)
                self.assertEqual(result["applied_patches"], ["moria_3_3_11.up2"])
                self.assertEqual(rows(db), [(1,), (2,), (3,)])
                self.assertEqual(fetch.call_count, 2)
            self.assertEqual(len(json.loads(Path(state).read_text())["patches"]), 2)

    def test_new_patch_revision_rebases_from_full_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            db, state = str(Path(tmp, "db.sqlite")), str(Path(tmp, "state.json"))
            old = remote_info([patch(1, "old")])
            new = remote_info([patch(1, "new")])
            def fake_rebuild(_archive, path, build_indexes=False):
                make_db(path)
                return os.path.getsize(path)
            with mock.patch.object(source, "_download_zm3") as download, \
                    mock.patch.object(source, "rebuild_from_file",
                                      side_effect=fake_rebuild), \
                    mock.patch.object(source, "_bytes", side_effect=[
                        p3encode("INSERT INTO pelis VALUES (2,'Película','old');"),
                        p3encode("INSERT INTO pelis VALUES (3,'Película','new');")
                    ]):
                source.sync(db, state, info=old)
                source.sync(db, state, info=new)
            self.assertEqual(download.call_count, 2)
            self.assertEqual(rows(db), [(1,), (3,)])

    def test_failed_patch_never_changes_live_database_or_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            db, state = str(Path(tmp, "db.sqlite")), str(Path(tmp, "state.json"))
            make_db(db)
            Path(state).write_text(json.dumps({"sha": "full-1",
                                               "repo": "Example/Catalogue"}))
            info = remote_info([patch(1, "patch-one")])
            with mock.patch.object(source, "_bytes", return_value=p3encode(
                    "INSERT INTO pelis VALUES (1, 'bad duplicate', 'broken');")):
                with self.assertRaises(sqlite3.IntegrityError):
                    source.sync(db, state, info=info)
            self.assertEqual(rows(db), [(1,)])
            self.assertEqual(json.loads(Path(state).read_text())["sha"], "full-1")
            self.assertFalse(Path(db + ".building").exists())

    def test_state_json_loss_does_not_replay_non_idempotent_sql(self):
        with tempfile.TemporaryDirectory() as tmp:
            db, state = str(Path(tmp, "db.sqlite")), str(Path(tmp, "state.json"))
            info = remote_info([patch(1, "patch-one")])
            def fake_rebuild(_archive, path, build_indexes=False):
                make_db(path)
                return os.path.getsize(path)
            with mock.patch.object(source, "_download_zm3"), \
                    mock.patch.object(source, "rebuild_from_file",
                                      side_effect=fake_rebuild), \
                    mock.patch.object(source, "_bytes", return_value=p3encode(
                        "INSERT INTO pelis VALUES (2,'Película','2026-11-02');")) as fetch:
                source.sync(db, state, info=info)
                os.remove(state)
                self.assertFalse(source.update_required(db, state, info))
                changed, _ = source.sync(db, state, info=info)
                self.assertFalse(changed)
                self.assertEqual(fetch.call_count, 1)
            self.assertEqual(rows(db), [(1,), (2,)])

    def test_legacy_plain_sql_preserves_question_marks(self):
        # Historical .upN files could be UTF-8 SQL instead of p3b64.
        plain = "INSERT INTO pelis VALUES (2,'¿Qué?', '2025-06-04');"
        self.assertEqual(catalogue._decode_up(plain.encode("utf-8")), plain)

    def test_catalogue_indexes_support_listing_and_latest_episodes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp, "catalogue.sqlite"))
            make_db(path)
            catalogue._index(path)
            with sqlite3.connect(path) as conn:
                for table, expected in (
                    ("pelis", "ix_pelis_cat_upd"),
                    ("series", "ix_series_cat_upd"),
                    ("enlaces_series", "ix_es_tmdb_upd"),
                ):
                    names = {row[1] for row in conn.execute(
                        "PRAGMA index_list('%s')" % table)}
                    self.assertIn(expected, names)

    def test_retry_mirrors_palantir_four_download_attempts(self):
        calls = []
        def attempt():
            calls.append("x")
            if len(calls) < 4:
                raise IOError("temporary")
            return True
        with mock.patch.object(source.time, "sleep") as sleeper:
            self.assertTrue(catalogue._retry(attempt))
        self.assertEqual(len(calls), 4)
        self.assertEqual([v.args[0] for v in sleeper.call_args_list], [2, 4, 8])

    def test_snapshot_commit_after_patch_skips_old_incremental(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp, "db.sqlite"))
            make_db(db)
            state = {"sha": "full-1", "repo": "Example/Catalogue"}
            info = remote_info([patch(1, "stale", "2026-10-31T23:00:00")])
            rebuild, pending, desired = catalogue._plan(db, state, info)
            self.assertFalse(rebuild)
            self.assertEqual(pending, [])
            self.assertEqual(desired, [])


if __name__ == "__main__":
    unittest.main()
