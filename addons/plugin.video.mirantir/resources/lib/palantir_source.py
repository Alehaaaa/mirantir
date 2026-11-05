# -*- coding: utf-8 -*-
"""Locate Palantir's active catalogue repository from current release metadata.

No database server address is built in. Public release repository references
are used only for bootstrap, alongside Palantir's own local source.txt.
"""

import base64
import io
import json
import os
import re
import urllib.request
import zipfile
import urllib.parse
import xml.etree.ElementTree as ET

# This is the Palantir add-on *distribution index*, not a database address.
# It can be overridden without editing Mirantir. No DB repo is hardcoded.
ADDON_REPO_XML = "https://palantir.5g.in/Repo/addons.xml"
# Public add-on distribution, NOT the catalogue/database repository.
PALANTIR_RELEASE_REPO = "palantirsource/palantir"
ADDON_ID = "plugin.video.palantir3"
UA = "mirantir/1.0"


def _json(url):
    headers = {"User-Agent": UA, "Accept": "application/vnd.github+json"}
    # In CI, authenticate only to GitHub itself (never to source.txt mirrors).
    token = os.environ.get("GITHUB_TOKEN")
    if token and urllib.parse.urlsplit(url).hostname == "api.github.com":
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, headers=headers)
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


def _repo_from_zip(data):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        matches = [n for n in archive.namelist()
                   if n.endswith("/libs/ioiiIII11.md")]
        if not matches:
            raise ValueError("Palantir database module missing from ZIP")
        return _repo_from_md(archive.read(matches[0]))


def _repo_from_index(state):
    """Optional Kodi repository-index bootstrap (also supports custom mirrors)."""
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

    package = "%s-%s.zip" % (ADDON_ID, version)
    template = os.environ.get("PALANTIR_ADDON_ZIP_URL")
    url = (template.format(version=version, addon_id=ADDON_ID)
           if template else urllib.parse.urljoin(index, ADDON_ID + "/" + package))
    return _repo_from_zip(_bytes(url)), version, index


def _repo_from_releases(state):
    """Follow live public Palantir release ZIPs, not a fixed catalogue URL.

    Use the ZIP blob SHA as the cache key: an add-on may be re-uploaded
    without incrementing its version. The Github API request is small;
    the multi-megabyte ZIP is downloaded only if its SHA changes.
    """
    source = _normalize_source(
        os.environ.get("PALANTIR_RELEASE_REPO") or PALANTIR_RELEASE_REPO)
    if not source:
        raise ValueError("invalid Palantir release repository")
    index = _api_base(source) + "/contents"
    matches = []
    for item in _json(index):
        name = item.get("name", "")
        match = re.fullmatch(r"plugin\.video\.palantir3-(\d+(?:\.\d+)+)\.zip", name)
        if match and item.get("sha") and item.get("download_url"):
            matches.append((tuple(map(int, match.group(1).split("."))), item))
    if not matches:
        raise ValueError("no Palantir releases published")
    ver, latest = max(matches, key=lambda entry: entry[0])
    version = ".".join(map(str, ver))
    if (state.get("palantir_index") == index
            and state.get("palantir_version") == version
            and state.get("palantir_release_sha") == latest["sha"]
            and state.get("palantir_repo")):
        return state["palantir_repo"], version, index
    repo = _repo_from_zip(_bytes(latest["download_url"]))
    state["palantir_release_sha"] = latest["sha"]
    return repo, version, index


def _derive_repo(state):
    """Prefer Palantir's live GitHub releases to an unverified legacy index.

    Explicit PALANTIR_ADDON_INDEX_URL wins, useful for installations with a
    custom upstream. Otherwise use public release repository, then legacy
    repository index as a last resort.
    """
    if os.environ.get("PALANTIR_ADDON_INDEX_URL"):
        return _repo_from_index(state)
    try:
        return _repo_from_releases(state)
    except Exception:
        return _repo_from_index(state)



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


def load_state(state_path):
    try:
        with open(state_path) as f:
            return json.load(f)
    except Exception:
        return {}


