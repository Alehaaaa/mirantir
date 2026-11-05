"""Offline regression tests for Palantir catalogue source discovery."""
import base64
import io
import json
import os
from pathlib import Path
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


def encoded_md(code):
    data = base64.b85encode(code.encode("utf-8"))
    t = len(data) // 3
    return data[t:2*t] + data[2*t:][::-1] + data[:t]


def info(repo, **kwargs):
    return {"repo": repo, "name": "moria_3_3_12.zm3",
            "sha": "new-sha", "url": "https://example.com/catalogue.zm3",
            "commit": "2026-11-05T10:00:00Z"}


class SourceDiscoveryTests(unittest.TestCase):
    def test_decodes_original_database_module_without_executing_it(self):
        code = "DB_API = 'https://api.github.com/repos/OtherOwner/NewCatalogue'"
        self.assertEqual(discovery._repo_from_md(encoded_md(code)),
                         "OtherOwner/NewCatalogue")

    def test_source_txt_takes_priority_and_accepts_original_api_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "source.txt").write_text(
                "https://api.github.com/repos/custom/catalogue\n", encoding="utf-8")
            with mock.patch.dict(os.environ, {"PALANTIR_ADDON_DIR": tmp}), \
                    mock.patch.object(discovery, "_derive_repo", side_effect=AssertionError(
                        "remote discovery should not run")), \
                    mock.patch.object(discovery, "_newest", side_effect=info) as newest:
                found = source.discover()
            self.assertEqual(found["repo"], "https://api.github.com/repos/custom/catalogue")
            newest.assert_called_once_with("https://api.github.com/repos/custom/catalogue")

    def test_current_release_wins_over_old_but_still_online_repo(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_file = os.path.join(tmp, "state.json")
            Path(state_file).write_text(json.dumps({"source_repo": "Old/Repo"}))
            with mock.patch.dict(os.environ, {"PALANTIR_ADDON_DIR": tmp}), \
                    mock.patch.object(discovery, "_derive_repo", return_value=(
                        "New/Repo", "3.3.12", "https://example.com/addons.xml")), \
                    mock.patch.object(discovery, "_newest", side_effect=info) as newest:
                found = source.discover(state_file)
            self.assertEqual(found["repo"], "New/Repo")
            newest.assert_called_once_with("New/Repo", preferred_version="3.3.12")
            persisted = json.loads(Path(state_file).read_text())
            self.assertEqual(persisted["source_repo"], "New/Repo")
            self.assertEqual(persisted["palantir_version"], "3.3.12")
            self.assertEqual(persisted["source_kind"], "current-palantir")

    def test_installed_module_used_when_remote_index_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp, "libs")
            folder.mkdir()
            (folder / "ioiiIII11.md").write_bytes(encoded_md(
                'db = "https://api.github.com/repos/Installed/Database"'))
            with mock.patch.dict(os.environ, {"PALANTIR_ADDON_DIR": tmp}), \
                    mock.patch.object(discovery, "_derive_repo", side_effect=OSError("offline")), \
                    mock.patch.object(discovery, "_newest", side_effect=info):
                found = source.discover()
            self.assertEqual(found["repo"], "Installed/Database")

    def test_cached_source_is_last_resort(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "state.json")
            path.write_text(json.dumps({"source_repo": "Cached/Repo"}))
            with mock.patch.dict(os.environ, {"PALANTIR_ADDON_DIR": tmp}), \
                    mock.patch.object(discovery, "_derive_repo", side_effect=OSError("offline")), \
                    mock.patch.object(discovery, "_newest", side_effect=info):
                found = source.discover(str(path))
            self.assertEqual(found["repo"], "Cached/Repo")
            self.assertEqual(json.loads(path.read_text())["source_kind"], "cached")

    def test_remote_version_reuses_cached_decoded_repo(self):
        index = "https://index.example/Repo/addons.xml"
        state = {"palantir_index": index, "palantir_version": "3.3.12",
                 "palantir_repo": "Current/Repo"}
        xml = b'<addons><addon version="3.3.12" id="plugin.video.palantir3" /></addons>'
        with mock.patch.dict(os.environ, {"PALANTIR_ADDON_INDEX_URL": index}), \
                mock.patch.object(discovery, "_bytes", return_value=xml) as read:
            value = discovery._derive_repo(state)
        self.assertEqual(value, ("Current/Repo", "3.3.12", index))
        read.assert_called_once_with(index)

    def test_downloads_changed_original_release_and_decodes_its_source(self):
        index = "https://index.example/Repo/addons.xml"
        xml = b'<addons><addon id="plugin.video.palantir3" version="3.3.12" /></addons>'
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as package:
            package.writestr("plugin.video.palantir3/libs/ioiiIII11.md",
                             encoded_md('x="https://api.github.com/repos/Live/Repo"'))
        with mock.patch.dict(os.environ, {"PALANTIR_ADDON_INDEX_URL": index}), \
                mock.patch.object(discovery, "_bytes", side_effect=[xml, buf.getvalue()]) as read:
            result = discovery._derive_repo({"palantir_version": "3.3.11"})
        self.assertEqual(result, ("Live/Repo", "3.3.12", index))
        self.assertEqual(read.call_args_list[-1].args[0],
                         "https://index.example/Repo/plugin.video.palantir3/"
                         "plugin.video.palantir3-3.3.12.zip")

    def test_invalid_live_repo_does_not_prevent_cached_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_file = str(Path(tmp, "state.json"))
            Path(state_file).write_text(json.dumps({"source_repo": "Cached/Repo"}))
            with mock.patch.dict(os.environ, {"PALANTIR_ADDON_DIR": tmp}), \
                    mock.patch.object(discovery, "_derive_repo", return_value=(
                        "Expired/Repo", "3.3.12", "https://example.com/addons.xml")), \
                    mock.patch.object(discovery, "_newest", side_effect=lambda repo, **kwargs:
                                      None if repo == "Expired/Repo" else info(repo)):
                found = source.discover(state_file)
            self.assertEqual(found["repo"], "Cached/Repo")
            self.assertNotIn("palantir_version", json.loads(Path(state_file).read_text()))

    def test_sync_does_not_overwrite_discovery_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp, "moria.cm3")
            state_file = Path(tmp, "state.json")
            db.write_bytes(b"database-present")
            state_file.write_text(json.dumps({"sha": "new-sha"}))

            def discovered(path):
                state = json.loads(Path(path).read_text())
                state["source_repo"] = "Live/Repo"
                Path(path).write_text(json.dumps(state))
                return info("Live/Repo")

            with mock.patch.object(catalogue, "discover", side_effect=discovered):
                changed, _ = source.sync(str(db), str(state_file))
            self.assertFalse(changed)
            self.assertEqual(json.loads(state_file.read_text())["source_repo"], "Live/Repo")

    def test_github_release_source_refreshes_when_zip_sha_changes(self):
        def release_zip(repository):
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as z:
                z.writestr("plugin.video.palantir3/libs/ioiiIII11.md",
                           encoded_md("x = 'https://api.github.com/repos/" +
                                      repository + "'"))
            return buf.getvalue()

        index = "https://api.github.com/repos/palantirsource/palantir/contents"
        old = {"name": "plugin.video.palantir3-3.3.11.zip",
               "sha": "old-zip-sha", "download_url": "https://example.com/zip"}
        latest = dict(old, sha="new-zip-sha")
        state = {"palantir_index": index, "palantir_version": "3.3.11",
                 "palantir_repo": "First/DB",
                 "palantir_release_sha": "old-zip-sha"}
        with mock.patch.dict(os.environ, {"PALANTIR_RELEASE_REPO": "palantirsource/palantir"}), \
                mock.patch.object(discovery, "_json", return_value=[old]), \
                mock.patch.object(discovery, "_bytes") as get:
            self.assertEqual(discovery._repo_from_releases(state)[0], "First/DB")
            get.assert_not_called()
        with mock.patch.dict(os.environ, {"PALANTIR_RELEASE_REPO": "palantirsource/palantir"}), \
                mock.patch.object(discovery, "_json", return_value=[latest]), \
                mock.patch.object(discovery, "_bytes",
                                  return_value=release_zip("Second/DB")) as get:
            found = discovery._repo_from_releases(state)
        self.assertEqual(found, ("Second/DB", "3.3.11", index))
        self.assertEqual(state["palantir_release_sha"], "new-zip-sha")
        get.assert_called_once_with("https://example.com/zip")

    def test_public_release_falls_back_to_legacy_index(self):
        with mock.patch.dict(os.environ, {"PALANTIR_ADDON_INDEX_URL": ""},
                             clear=False), \
                mock.patch.object(discovery, "_repo_from_releases",
                                  side_effect=OSError("releases down")), \
                mock.patch.object(discovery, "_repo_from_index",
                                  return_value=("From/Index", "3.3.11", "index")):
            result = discovery._derive_repo({})
        self.assertEqual(result[0], "From/Index")

    def test_public_api_is_compact_and_backward_compatible(self):
        self.assertEqual(set(source.__all__),
                         {"discover", "load_state", "sync", "update_required"})
        self.assertTrue(all(callable(getattr(source, key))
                            for key in source.__all__))

    def test_no_database_repo_hardcoded(self):
        file_text = Path(discovery.__file__).read_text()
        self.assertNotIn("Maniac2017/Mipal2025", file_text)
        self.assertNotIn("DEFAULT_DB_REPO", file_text)


if __name__ == "__main__":
    unittest.main()
