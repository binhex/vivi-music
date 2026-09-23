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
- On-device checklist for patch 01: download a song and confirm it lands in `Music/Vivi`; re-download
  it (must overwrite, not duplicate); pick a custom folder and confirm the file lands there; reset the
  folder (or revoke its access) and confirm the fallback to `Music/Vivi`; switch the feature off and
  confirm nothing is written; play a downloaded song in airplane mode to confirm offline playback is
  untouched.
