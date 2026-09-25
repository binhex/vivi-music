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
  *Settings -> Storage -> Download format -> Folder format*. It defaults to `%artist%/%album%`;
  `%artist%`, `%album%`, `%year%`, `%title%`, `%songId%`, `%quality%` and `%tracknumber%` are supported,
  an unresolvable token becomes `Unknown Artist` / `Unknown Album` / `Unknown Year` / `Unknown Quality`,
  and an explicitly emptied template means flat output directly in the root. In a *folder* format
  `%artist%` is the artist the album is filed under - the credited album artist when the library knows it,
  or the fixed `Various Artists` for a compilation, defined as an album whose credit performs none of its
  tracks, or (with no credit stored) one shared by at least two performers where no performer owns half of
  it. The *file-name* format keeps using the track's own artist, so a compilation's folder is uniform while
  each file name still names its performer.
- Optional **file-name** template in *Settings -> Storage -> Download format -> File format*, defaulting to
  `%tracknumber% - %artist% - %album% - %title%`, so an album download lands as
  `10 - Metallica - Master Of Puppets - Battery.webm` and sorts in album order. A part whose token has no
  value disappears together with its separator, and an emptied or blank file template means the built-in
  default. Track numbers come from the album position already stored in `song_album_map` (two digits up to
  99, raw above), so a download taken from a search or playlist, which has no album row, simply carries no
  number.
- **Download recovery** for the "download sits there forever" case: a patch-owned watchdog reads the
  download index every 15 seconds and, for a download that has made no progress for 90 seconds - or that has
  been running for 5 minutes even while slowly crawling - restarts it, and retries a failed download once
  per session, only when the failure is younger than 10 minutes and happened while the watchdog was watching
  (a failed row outlives the app, so those two bounds together stop a dead download being re-queued and
  re-notified on every launch, and a row that Media3 rebuilds never refills that one retry).
  A restart keeps the bytes already cached (Media3 re-queues the download and the cache serves the finished
  prefix), and it re-adds the request rather than setting a stop reason, so the download never passes through
  the stopped state that would make the app forget it was downloaded.
  Each check reads only the watching rows - queued, downloading and failed - a download missing from a check
  is forgotten, and a row that Media3 re-creates gives the restart budget back (the retry budget only when
  the rebuild is the watchdog's own retry, so a re-download by the user is never refused a retry); before
acting, the row is read again so a download the user deleted cannot be brought back to life. Nothing at all is touched
    while the device is offline - a
  network that reports internet access but never validates (a captive portal) counts as offline - queued or
  stopped downloads are never restarted, restarts are capped at two per download, each check runs on the
  thread Media3 requires the manager to be used from, and every recovery is logged under the
  `DownloadWatchdog` tag.
- Optional **clean up names** switch (on by default) inside the File format dialog: a trailing bracket tag
  from a fixed list (`(Official Video)`, `[HD]`, `(Official Audio)`, `[4K]`, ...) and a trailing `- Topic`
  artist suffix are removed before either template is expanded. `(Remastered)`, `(Live)` and `(feat. ...)`
  are deliberately kept.
- The private Media3 download cache is never modified, so an export failure cannot break offline
  playback: the copy is read from the cache and only the new file is touched.

Footprint: 12 new files, plus **80 added lines** in four upstream files -
`DownloadUtil.kt` (constructor parameter + one call in the `STATE_COMPLETED` branch),
`StorageSettings.kt` (one call to `LocalDownloadSettingsGroup()`),
`app/build.gradle.kts` (Kover wiring, the `AlbumArtist*` coverage scope and `testImplementation(libs.junit)`)
and `DatabaseDao.kt` (a suspend query for the album position plus three for the album's credited artists
and performer spread). The watchdog's share of that is small and reversible: one constructor parameter, one
`start` call, and closing the index cursor the same `init` block used to leak, plus the one Kover filter line
for its pure unit - so removing the feature again means deleting the patch's own files and reverting those
few lines.

## Known limitations (accepted for now)

| Limitation | Notes |
| --- | --- |
| Only downloads that finish *after* the feature is on get exported | There is no sweep for the existing library and no retry for a failed export. A one-shot "export existing downloads" action is the natural follow-up. |
| Same artist + title means one file | Two different songs that share artist and title (likely when the artist is unknown, e.g. `Unknown Artist - Intro.m4a`) map to the same name and the later export replaces the earlier one. Adding `%songId%` to the template avoids it. |
| Changing the template does not move existing files | Only new exports use the new structure; files already written stay where they are, and a copy written by the Music/Vivi fallback is not cleaned up when the chosen folder starts working again. Reorganising them stays out of scope. |
| A directory carries the export's name | A child that is a folder is left alone and logged, so a folder is never deleted recursively. The export is then staged under the requested name, which the provider uniquifies, so repeated exports add copies rather than replacing that name. |
| A cancelled export still finishes the copy | The copy loop has no suspension points (blocking IO on purpose), so cancellation is observed after the file is written. The result is correct and idempotent. |
| The new strings are English only | The `download_folder*` and `download_format*` strings live in the default locale; every other locale falls back to English until translated. |
| A credit that performs nothing becomes `Various Artists` | An album credited to a composer, a label or a compilation pseudo-artist rather than to its performers is filed under `Various Artists`. That credit is deliberately discarded: it is not a name the album's files belong under, and matching the localised text of the pseudo-artist instead would make the folder tree depend on the app language. |
| A two-track release by two artists is not detected | The performer-spread rule needs the top performer to own *under* half of the album, and on a two-track release one performer owns exactly half, so such an album is not treated as a compilation and each track keeps its own artist folder - the split this patch removes for larger compilations. The credited-artist rule still catches it whenever the album header was stored. |
| Rule B divides by the stored track list, not by the tracks that have artist data | `albumSongCount` counts every song the album has stored, including tracks whose metadata lists no artist. An album where the top known performer owns most of the tracks *with* artist data can therefore still be filed under `Various Artists`. The credited-artist rule (Rule A) is unaffected. |
| A restarted download reuses its cached stream URL until that URL expires | The watchdog can interrupt a stalled transfer and re-queue it, but it cannot force a fresh URL: while the cached URL is still inside its lifetime the restart reuses it. A URL that fails before its stated expiry is only replaced once Media3 itself marks the download failed and clears the cache entry, and a URL that hangs rather than erroring spends both restart budgets and is then left alone. Forcing a fresh URL would mean changing the stream resolver, which is upstream code, so it stays out of the patch. |
| A delete landing at the same instant as a recovery can still be undone | Before acting, the watchdog re-reads the row and skips a download that has gone or moved on, which narrows the window to the gap between that read and Media3 processing the re-added request on its own thread. Closing it completely would need an atomic compare-and-set that Media3 does not offer. |
| A recovery runs without the download service | The manager is called directly, because `DownloadService.sendAddDownload` starts the service with `startService`, which Android forbids from the background - and a stalled download is usually found there. A recovery started while the app is in the background therefore runs without the service holding the process, so the OS may park it until the app is next opened; the request keeps its identity and its cached bytes and carries on then. |
| The watchdog's timings are fixed defaults | 90 seconds without progress, 5 minutes total, two restarts, one retry per session for a failure younger than 10 minutes that happened while the watchdog was watching, checked every 15 seconds. Telling the watchdog's own retry apart from a user's re-download by timing does not work (a frozen process notices either one late), so the retry is simply per session, and they are constants in the patch rather than settings - a device with an unusually slow connection will see the restarts harmlessly, because the download resumes from its cached prefix. |
| Rule A compares names, so a different script or romanisation can misfile an album | Only whitespace, case, a trailing `- Topic` and a closed bracket-tag list are unified. A credit stored in a different script or romanisation from the performer (a native-script credit against romanised track rows, for example) therefore looks like "the credit performs none of the album" and the album is filed under `Various Artists`. The design deliberately trades that failure class for language independence. |
| Windows-reserved names are not rewritten | `CON`, `PRN`, `AUX`, `NUL`, `COM1`-`COM9` and `LPT1`-`LPT9` pass the sanitiser. Harmless on Android, but a tree copied to Windows or written to FAT/OTG media can be awkward to open. |
| The SAF folder is treated as Vivi's own export folder | SAF has no ownership column (unlike MediaStore's `OWNER_PACKAGE_NAME`), so an existing file with the same name is replaced. Point the feature at a dedicated folder if it already holds files from other tools. |
| A foreign file with the exact same name makes MediaStore rename ours | Our copy becomes `Name (1).m4a`, and later re-exports add `(2)`, `(3)`... because cleanup matches the exact display name. |
| Replacing an export is staged, not atomic across a crash | The new file is written as `Name.m4a.part` and renamed into place, so an interrupted copy leaves a `.part` file rather than truncating the previous export. The MediaStore path is protected by `IS_PENDING` instead. On providers that normalise extensions the leftover can appear as `Name.m4a.part.m4a`. |
| The extension follows the downloaded bytes | Extension and MIME are sniffed from the cached container (WebM/MP4/ADTS-AAC/MP3/FLAC/OGG) and only fall back to the stored format row: the audio quality setting can pick a different container after the download, so the row alone would mislabel the file. The MP3 check is an exact match on `audio/mpeg` / `audio/mp3`, so a playlist MIME such as `application/x-mpegURL` is not treated as an MP3 stream and a provider reporting something like `audio/x-mpeg` falls back to `.m4a`. |
| Deleting a download in the app leaves the exported file | Intentional: the exported file lives in the user's own Music folder, and the app does not delete user files. |
| API 26-28 exports are not in the media database | They land in `Android/data/<pkg>/files/Music/Vivi`, which the media scanner does not index, so only file managers see them. |
| Files go directly in the picked folder | No `Vivi` subfolder is created inside a SAF folder the user chose. |
| A provider that cannot report ownership leaves the old file alone | Cleanup only ever deletes rows this package owns. If a provider rejects the owner query, nothing is deleted: the previous export stays and MediaStore gives the new one a deduplicated name (for example `Name (1).m4a`). |
| A dot-leading artist or album makes a hidden folder | Folder segments keep a leading dot, which is what lets a template place a deliberate `.nomedia` marker. An artist or album whose name starts with a dot (for example `.38 Special`) therefore lands in a hidden folder that some media libraries skip. The file name itself is protected: a dot-leading file name is written with a `_` prefix. |
| No disc numbers | Nothing in the schema records a disc number, so `%disc%` does not exist; a multi-disc album numbers tracks continuously within one `song_album_map` row set. |
| An exotic separator can leave punctuation behind | The tidy pass collapses and trims `-`, `–`, `.`, `,`, `_` and whitespace. A template that separates parts with something else (for example `%tracknumber% ~ %title%`) can leave the `~` behind when the token is empty. The dialog preview shows the real result before saving. |
| A name longer than 240 bytes is elided in the middle | `Metallica - Master Of Puppets - 05 - The Thin...Not Be (Remastered).webm` keeps the start and the tail of the track name, joined by `...`, so the track name is never lost to a tail truncation. |
| Clean-up is metadata-only and not retroactive | Turning the switch on does not rename files that already exist, and it never edits text in the middle of a title. |

## Coverage gate and named debt

`Local Patch Build` enforces a Kover line-coverage gate of 95% over the JVM-testable scope. The filter
is explicit in `app/build.gradle.kts`:

- **Measured:** `DownloadFormat` (the pure token, path and naming rules), `AlbumArtist` (the pure
  album-artist rule) and `DownloadRecovery` (the pure stall/retry policy behind the watchdog) - a local
  JaCoCo run over the full unit suite reports 137/137 (`DownloadFormat`), 15/15 (`AlbumArtistKt`) and 83/83
  across every `DownloadRecovery*` class = 106/106 lines = **100%**; CI enforces the 95% bound with the Kover `includes`
  filters
  `com.music.vivi.playback.DownloadFormat*`, `com.music.vivi.playback.AlbumArtist*` and
  `com.music.vivi.playback.DownloadRecovery*` - the last one covering the policy, its observation and its
  action/phase enums, because they all share that prefix.
- **Excluded from the measured scope, because they need Robolectric or a device:** `DownloadFolderExporter`,
`SafFolders`, `LocalDownloadPrefs`, `DownloadUtil`, `LocalDownloadSettings`, `DownloadWatchdog`. The gate's
  `includes` filter limits measurement to `DownloadFormat*`, `AlbumArtist*` and `DownloadRecovery*`, so these
  are named debt here rather than listed in the build file.
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
git rebase origin/main        # new files + ~32 added lines in four upstream files: normally no conflict

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
  `Folder: <volume>/<path>` - the full path, not just the folder's own name - (not "Folder access
  lost"); pick the **same** folder again and confirm the grant
  survives; set the folder structure to `%artist%/%album%` and confirm a download lands in nested
  `Artist/Album/` folders under both roots; clear the template and confirm flat output, then press
  Reset and confirm the default returns; download a song and confirm it lands in that folder and
  plays; re-download it (must replace, not duplicate); reset the folder (or revoke its access) and
  confirm the fallback to `Music/Vivi`; switch the feature off and confirm nothing is written; play a
  downloaded song in airplane mode to confirm offline playback is untouched.
- On-device checklist for the file-name format: download a whole album and confirm the file manager lists
  it in album order with two-digit numbers (`... - 01 - ...`); download a song from search (no album row)
  and confirm the name has no number and no doubled `-`; turn the clean-up switch off and re-download a
  video-sourced track to confirm the `(Official Video)` tag comes back; with the switch on, confirm it is
  gone and that `(Remastered)` survives; set a long, silly template and confirm the name keeps its end and
  the extension; clear the file template and confirm the default returns.
- Debugging: `adb logcat -s DownloadFolderExporter LocalDownloadSettings` reports every export result
  (`Exported <id> as <name>`, or `Export failed ... cached download is intact`).
