# Mirantir

Kodi repository for **Mirantir**, with automatic add-on updates.

Repository URL: <https://alehaaaa.github.io/mirantir/>

## Install in Kodi

1. [Download `repository.mirantir-1.0.0.zip`](https://alehaaaa.github.io/mirantir/zips/repository.mirantir/repository.mirantir-1.0.0.zip).
2. In Kodi, open **Settings → Add-ons → Install from zip file** and select the downloaded ZIP.
3. Choose **Install from repository → Mirantir → Video add-ons → Mirantir**.

Kodi will subsequently discover new versions through `addons.xml` and update the add-on according to the user's update settings.

## Publish an update

1. Work directly in `addons/plugin.video.mirantir/`.
2. Increase the `version` in `addons/plugin.video.mirantir/addon.xml`.
3. Commit and push the source changes to `main`.

GitHub Actions automatically creates the versioned Kodi ZIP, regenerates `addons.xml` and `addons.xml.md5`, validates the repository, and commits the published artifacts. GitHub Pages then serves the update to Kodi.

For a local preview, run:

```sh
python3 tools/build_repo.py
python3 tools/check_repo.py
```

## Repository layout

- `addons/`: source for each published add-on.
- `zips/`: installable, versioned ZIP files and artwork served to Kodi.
- `addons.xml`: add-on index consumed by Kodi.
- `addons.xml.md5`: checksum Kodi uses to detect index changes.
- `tools/`: build and validation scripts.
