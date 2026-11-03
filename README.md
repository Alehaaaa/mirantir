# Mirantir

Kodi repository for **Palantir Local**, published as **Mirantir**, with automatic add-on updates.

Repository URL: <https://alehaaaa.github.io/Mirantir/>

## Install in Kodi

1. Download `repository.palantir.local-1.0.0.zip` from the repository's `zips/repository.palantir.local/` directory.
2. In Kodi, open **Settings → Add-ons → Install from zip file** and select the downloaded ZIP.
3. Choose **Install from repository → Mirantir → Video add-ons → Palantir Local**.

Kodi will subsequently discover new versions through `addons.xml` and update the add-on according to the user's update settings.

## Publish an update

1. Replace the source in `addons/plugin.video.palantir.local/` and increase the `version` in its `addon.xml`.
2. Run `python3 tools/build_repo.py`.
3. Run `python3 tools/check_repo.py` and commit every changed file.

The build is deterministic, and GitHub Actions rejects commits whose generated metadata or ZIP packages are stale.

## Repository layout

- `addons/`: source for each published add-on.
- `zips/`: installable, versioned ZIP files and artwork served to Kodi.
- `addons.xml`: add-on index consumed by Kodi.
- `addons.xml.md5`: checksum Kodi uses to detect index changes.
- `tools/`: build and validation scripts.
