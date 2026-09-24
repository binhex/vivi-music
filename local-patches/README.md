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
- Optional folder structure template applied under whichever root is active, edited in
  *Settings -> Storage -> Folder structure*. It defaults to `%artist%/%album%`; `%artist%`, `%album%`,
  `%year%`, `%title%`, `%songId%` and `%quality%` are supported, an unresolvable token becomes
  `Unknown Artist` / `Unknown Album` / `Unknown Year` / `Unknown Quality`, and an explicitly emptied
  template means flat output directly in the root.
- The private Media3 download cache is never modified, so an export failure cannot break offline
  playback: the copy is read from the cache and only the new file is touched.

Footprint: 7 new files, plus **5 added lines** in three upstream files -
`DownloadUtil.kt` (constructor parameter + one call in the `STATE_COMPLETED` branch),
`StorageSettings.kt` (one call to `LocalDownloadSettingsGroup()`) and
`app/build.gradle.kts` (`testImplementation(libs.junit)` for the new unit tests).

## Known limitations (accepted for now)

| Limitation | Notes |
| --- | --- |
| Only downloads that finish *after* the feature is on get exported | There is no sweep for the existing library and no retry for a failed export. A one-shot "export existing downloads" action is the natural follow-up. |
| Same artist + title means one file | Two different songs that share artist and title (likely when the artist is unknown, e.g. `Unknown Artist - Intro.m4a`) map to the same name and the later export replaces the earlier one. Adding `%songId%` to the template avoids it. |
| Changing the template does not move existing files | Only new exports use the new structure; files already written stay where they are. Reorganising them stays out of scope. |
| The SAF folder is treated as Vivi's own export folder | SAF has no ownership column (unlike MediaStore's `OWNER_PACKAGE_NAME`), so an existing file with the same name is replaced. Point the feature at a dedicated folder if it already holds files from other tools. |
| A foreign file with the exact same name makes MediaStore rename ours | Our copy becomes `Name (1).m4a`, and later re-exports add `(2)`, `(3)`... because cleanup matches the exact display name. |
| Replacing an export is staged, not atomic across a crash | The new file is written as `Name.m4a.part` and renamed into place, so an interrupted copy leaves a `.part` file rather than truncating the previous export. The MediaStore path is protected by `IS_PENDING` instead. |
| The extension follows the downloaded bytes | Extension and MIME are sniffed from the cached container (WebM/MP4/MP3/FLAC/OGG) and only fall back to the stored format row: the audio quality setting can pick a different container after the download, so the row alone would mislabel the file. |
| Deleting a download in the app leaves the exported file | Intentional: the exported file lives in the user's own Music folder, and the app does not delete user files. |
| API 26-28 exports are not in the media database | They land in `Android/data/<pkg>/files/Music/Vivi`, which the media scanner does not index, so only file managers see them. |
| Files go directly in the picked folder | No `Vivi` subfolder is created inside a SAF folder the user chose. |

## Coverage gate and named debt

`Local Patch Build` enforces a Kover line-coverage gate of 95% over the JVM-testable scope. The filter
is explicit in `app/build.gradle.kts`:

- **Measured:** `FolderTemplate` (the pure path and naming rules) - 64/65 lines = **98.5%**.
- **Excluded, because they need Robolectric or a device:** `DownloadFolderExporter`, `SafFolders`,
  `LocalDownloadPrefs`, `DownloadUtil`, `LocalDownloadSettings`.
- **Not measured at all (named debt):** the `canvas`, `innertube` and `lyricsProvider` modules. Wiring
  Kover into them means build-file contact in modules this patch never touches, and a 95% bound there
  would likely fail on pre-existing coverage. Agreed with the maintainer to record it as debt.
- **Pre-existing debt left alone (named):** `lyricsProvider/src/test/kotlin/com/music/musixmatch/MusixmatchTest.kt`
  `debugKaliUchis` contains no assertions - it prints only.

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
git diff origin/main -- app/ > local-patches/01-download-folder.patch   # app/ only: docs stay out of the patch
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
  `Folder: <name>` (not "Folder access lost"); pick the **same** folder again and confirm the grant
  survives; set the folder structure to `%artist%/%album%` and confirm a download lands in nested
  `Artist/Album/` folders under both roots; clear the template and confirm flat output, then press
  Reset and confirm the default returns; download a song and confirm it lands in that folder and
  plays; re-download it (must replace, not duplicate); reset the folder (or revoke its access) and
  confirm the fallback to `Music/Vivi`; switch the feature off and confirm nothing is written; play a
  downloaded song in airplane mode to confirm offline playback is untouched.
- Debugging: `adb logcat -s DownloadFolderExporter LocalDownloadSettings` reports every export result
  (`Exported <id> as <name>`, or `Export failed ... cached download is intact`).
