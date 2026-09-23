# Local patch set

This fork builds **upstream vivi-music + the patches in this directory**. No upstream file is ever
committed here, so `git merge upstream/main` is always conflict-free and a new upstream release can be
pulled in without touching our code.

## Layout

| Path | Purpose |
| --- | --- |
| `local-patches/*.patch` | One patch per feature, applied in filename order. |
| `local-patches/apply.sh` | Applies (or `--check`s) every patch against the current checkout. |
| `.github/workflows/local-build.yml` | Applies the patches to upstream `main`, builds a debug APK. |
| `.github/workflows/upstream-drift.yml` | Weekly canary: do the patches still apply to upstream `main`? |

## Build an APK

Actions -> **Local Patch Build** -> *Run workflow*.

- `flavor`: `foss` (default, no Play Services) or `gms` (Google Cast).
- `upstream_ref`: `main` by default; any branch or tag of upstream can be built instead.

The APK is attached to the run as `vivi-<flavor>-debug-<upstream-sha>`, and installs alongside the
official app because debug builds use `applicationIdSuffix = ".debug"`. A lint report is attached to
the same run.

Pushing to `main` also rebuilds automatically whenever `local-patches/**` changes. Upstream's own
`build.yml` triggers on every branch push too, so a push normally produces a `gms` APK as well.

## What patch 01 does

`01-download-folder.patch` writes every completed download out as a real audio file, so it is visible
in a file manager or any other music player:

- Default destination `Music/Vivi` - MediaStore on API 29+, the app-specific external music directory
  on API 26-28 (visible there and no runtime permission needed).
- Optional Storage Access Framework folder override in *Settings -> Storage -> Download folder*.
- The private Media3 download cache is never modified, so an export failure cannot break offline
  playback: the copy is read from the cache and only the new file is touched.

Footprint: 5 new files, plus **4 added lines** in two upstream files -
`DownloadUtil.kt` (constructor parameter + one call in the `STATE_COMPLETED` branch) and
`StorageSettings.kt` (one call to `LocalDownloadSettingsGroup()`).

## Known limitations (accepted for now)

| Limitation | Notes |
| --- | --- |
| Only downloads that finish *after* the feature is on get exported | There is no sweep for the existing library and no retry for a failed export. A one-shot "export existing downloads" action is the natural follow-up. |
| Same artist + title means one file | Two different songs that share artist and title (likely when the artist is unknown, e.g. `Unknown Artist - Intro.m4a`) map to the same name and the later export replaces the earlier one. Fix would be a song-id suffix in `buildFileName`. |
| A failed re-export removes the previous exported file | The old file is deleted before the new copy is written. The download itself is never touched, so the audio is not lost - only the visible file until the next successful export. MediaStore keeps partial files out of the media database via `IS_PENDING`. |
| Deleting a download in the app leaves the exported file | Intentional: the exported file lives in the user's own Music folder, and the app does not delete user files. |
| API 26-28 exports are not in the media database | They land in `Android/data/<pkg>/files/Music/Vivi`, which the media scanner does not index, so only file managers see them. |
| Files go directly in the picked folder | No `Vivi` subfolder is created inside a SAF folder the user chose. |

## Updating for a new upstream release

Work in a clone of upstream, with the patch applied on a normal branch:

```bash
# once
git remote add fork https://github.com/binhex/vivi-music.git
git fetch origin main

# put the current patch on a branch you can rebase
git switch -c local/download-folder origin/main
git apply local-patches/01-download-folder.patch   # from this repo's checkout
git commit -am "local: save completed downloads to a user-visible folder"

# ...later, after upstream releases...
git fetch origin main
git rebase origin/main        # new files + 4 lines: normally no conflict

# publish the regenerated patch
git fetch fork main
git switch -c fork-main fork/main
git diff origin/main local/download-folder > local-patches/01-download-folder.patch
git commit -am "local: rebase patch 01 onto upstream $(git rev-parse --short origin/main)"
git push fork fork-main:main
git switch local/download-folder
```

If upstream did edit one of the touched lines, `git rebase` reports the file and you resolve it there.
`upstream-drift.yml` failing is the same signal, but earlier and without needing a build.

To check by hand before pushing:

```bash
git worktree add --detach /tmp/vivi-check origin/main
cd /tmp/vivi-check && /path/to/this/repo/local-patches/apply.sh --check
```

## Notes

- GitHub disables scheduled workflows after 60 days without repository activity. If the weekly drift
  check stops running, re-enable it from the Actions tab.
- On-device checklist for patch 01: pick a folder and confirm the setting immediately reads
  `Folder: <name>` (not "Folder access lost"); download a song and confirm it lands in that folder;
  re-download it (must overwrite, not duplicate); reset the folder (or revoke its access) and confirm
  the fallback to `Music/Vivi`; switch the feature off and confirm nothing is written; play a
  downloaded song in airplane mode to confirm offline playback is untouched.
- Debugging: `adb logcat -s DownloadFolderExporter LocalDownloadSettings` reports every export result
  (`Exported <id> as <name>`, or `Export failed ... cached download is intact`).
