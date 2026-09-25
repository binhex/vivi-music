# Album-artist folders for downloaded compilations - design

Date: 2026-09-24
Status: approved (pending implementation)
Extends: `local-patches/01-download-folder.patch` (see Delivery)

## Goal

A download taken from a various-artists album must land in **one** folder, not one folder per performer.
With the folder structure at its default `%artist%/%album%` and the album set to "QUEENDOM2 FINAL", which
is performed by six different artists, every track must go to `Music/Vivi/Various Artists/QUEENDOM2 FINAL/`
instead of `Music/Vivi/HYOLYN/QUEENDOM2 FINAL/`, `Music/Vivi/WJSN/QUEENDOM2 FINAL/`, and so on.

The folder token stops meaning "the artist of this track" and starts meaning "the artist this album is
filed under": the album's credited artist when the library knows it, `Various Artists` when the album is a
compilation, and the track's own artist when the library knows nothing better. The file-name template is
untouched, so the performer of each track is still visible in the file name.

## Context

Findings from reading the code that shape the design. The download folder feature lives in the patch, so
of the files named below only `DatabaseDao.kt` and `app/build.gradle.kts` are upstream files, and both are
already patch hooks; everything else is created by patch 01.

- **Folder resolution is one pure unit.** `DownloadFormat.expand(input, template)` resolves each segment of
  the folder template; `resolve("artist", ...)` currently returns
  `input.artists.joinToString(", ").ifBlank { UNKNOWN_ARTIST }`, and `input.artists` is the *track's*
  artist list, mapped from `Song.artists` by the `Song.toTemplateInput` extension in
  `DownloadFolderExporter.kt`. The same `Input` feeds the file-name template, which is why the two
  templates share one artist value today.
- **The library does store album-level artists.** `album_artist_map` holds the album header's credited
  artists, in display order. `DatabaseDao.insert(albumPage)` populates it from
  `albumPage.album.artists` on every album page that is browsed or synced, and the `Album` /
  `AlbumWithSongs` wrappers already expose it as a Room `@Relation`. A credited name whose
  `navigationEndpoint` has no artist browse id (which is how YouTube Music marks "Various Artists") is
  inserted as a normal `ArtistEntity` with a generated local id, so the *name* is stored even when the
  pseudo-artist has no channel.
- **Per-track performers are stored too.** `song_artist_map` holds each track's artists, and
  `song_album_map` links songs to an album, so "which artists perform this album, and how many tracks
  each" is one grouped query away. `song_album_map` is also what `%tracknumber%` already reads.
- **The credited name is localised.** YouTube Music sends the text the device language asks for, so the
  pseudo-artist may arrive as `Various Artists`, `Verschiedene Interpreten` or `Artistes variés`.
  (Confirmed against the rustypipe parser, which flags an album when the header run has no artist link and
  the text equals the localised `VARIOUS_ARTISTS` string.) Matching that literal text is therefore not a
  portable way to detect a compilation - the structural comparison below is.
- **`DownloadUtil` inserts a bare `SongEntity`** when a row is missing, so a download taken straight from
  search or a playlist has no album row and no artist rows. Nothing can be derived for those, and nothing
  changes for them.
- **The exporter already has the pattern for best-effort lookups.** `albumPosition(songId, albumId)`
  rethrows `CancellationException`, logs anything else and returns null, because `export()` is
  fire-and-forget and must never throw.
- **Coverage scope is explicit.** The Kover gate covers `com.music.vivi.playback.DownloadFormat*` at 95%
  lines; a new pure unit has to be added to that scope to be held to the same bar.

## Decisions

| Decision | Choice | Rationale |
| --- | --- | --- |
| Which template changes | The **folder** template only | A compilation's folder must be uniform, but the file name is the one place where the real performer is still visible; `HYOLYN - QUEENDOM2 FINAL - 01 - Waka Boom.m4a` stays useful inside a `Various Artists` folder. |
| Resolution order for folder `%artist%` | Compilation, then credited album artist, then track artist, then `Unknown Artist` | The credited artist is what the album page shows, so the folder matches the app; the track artist remains the fallback, which keeps today's behaviour for everything the library knows nothing about. |
| Compilation rule, credited case (**Rule A**) | The album has credited artists, at least one performer row exists, and **no** credited artist performs any of the album's tracks | Locale-independent, so the localised "Various Artists" text never has to be matched. Using name comparison instead of the pseudo-artist's missing link needs no new column. |
| Compilation rule, uncredited case (**Rule B**) | No credited artists, at least two performers, and the top performer is on **under half** the album's tracks (`top * 2 < albumSongCount`) | Catches a compilation whose album header was never stored, without mistaking an album that has a single guest verse for a compilation. |
| Credit mismatch with no performer rows | Not a compilation | Otherwise an album whose tracks have no artist rows would be "vacuously" credited to a stranger and mislabelled. |
| Name comparison | Trimmed, case-folded, and tidied like a name | The schema can hold two `artist` rows with the same name and different ids (the generated-local-id path), and a credited name and a performer name that differ only in case are the same artist. Tidying the same way the naming rules do also makes a credited name that only carries a video suffix (`Metallica - Topic`) the same artist as the performer, so a normal album is not filed under `Various Artists`. |
| Result value | The credited names joined with `", "`, in display order, de-duplicated | Matches the existing multi-artist joining rule for track artists, so a split album credited to two artists becomes one folder instead of two. |
| Compilation folder name | The fixed ASCII constant `Various Artists` | Consistent with the existing `Unknown Artist` / `Unknown Album` decision that placeholders are never localised, so an English and a German install produce the same tree. |
| Opt-out | None; always on | A folder organiser is expected to file an album under its album artist, and a switch would double the branches and the tests for a case nobody has asked for. |
| Where the rule lives | A new pure `playback/AlbumArtist.kt`, not inside `DownloadFormat` | `DownloadFormat` owns pure path and name syntax; the album-artist rule is a different concern and is easier to test alone. `DownloadFormat` gains one field, not a rule. |
| Database reads | Three small `DatabaseDao` queries, added to the patch's existing `DatabaseDao.kt` hook | The patch already edits that file for `albumIndex`. With the single Kover filter line in `app/build.gradle.kts`, these queries are the whole of this design's added upstream contact. |
| When the reads run | Only when the folder template actually contains `%artist%` | Mirrors the existing "preference read first, so a disabled feature costs nothing" rule: a template like `%album%/%year%` must not pay for three database reads. |
| Reads fail | Log and fall back to the track artist | Same contract as `albumPosition`: `export()` never throws and the cached download is never touched. |

### Documented consequences

- An album credited to someone who performs none of it - a composer or label credit, a score performed by
  an orchestra - is filed under `Various Artists` rather than under that credit. This is Rule A working as
  specified: the credit is not a useful folder name when nobody on the album is that artist.
- A two-track release by two artists is not detected: its top performer owns exactly half, and Rule B needs
  under half. Rule A still catches it whenever the album's credited artists are stored.
- Only downloads that start from a library row with an album can be detected. A download straight from
  search keeps today's `Unknown Artist` behaviour.

## Design

### Units and footprint

| File | Change |
| --- | --- |
| **NEW** `app/src/main/kotlin/com/music/vivi/playback/AlbumArtist.kt` | `const val VARIOUS_ARTISTS = "Various Artists"`, the `AlbumPerformerTracks(artist, tracks)` Room projection, and the pure rule `folderArtists(creditedArtists, performerTracks, albumSongCount): List<String>?`, where `null` means "fall back to the track artists". No Android imports, so it runs as a JVM unit test and stays inside the coverage gate. |
| `app/src/main/kotlin/com/music/vivi/playback/DownloadFormat.kt` | `Input` gains `folderArtists: List<String>? = null`. `cleaned()` tidies it exactly like `artists`. The folder branch of `resolve("artist", ...)` becomes `input.folderArtists ?: input.artists`, where an empty or all-blank list counts as absent; the file-name branch is unchanged. New `internal usesArtistToken(template): Boolean`, matching the existing `internal resolvedSegments`, so the exporter can tell whether the lookups are needed without duplicating the token regex. |
| `app/src/main/kotlin/com/music/vivi/playback/DownloadFolderExporter.kt` | One new top-level `internal suspend fun albumFolderArtists(database: MusicDatabase, albumId: String?): List<String>?`, guarded at the call site by `DownloadFormat.usesArtistToken` and called from `exportLocked` when `Input` is built; it is shared with the settings preview, which is why it is not private. The three writers, the SAF walk, the MediaStore publish flow and `copyFromCache` are untouched. |
| `app/src/main/kotlin/com/music/vivi/db/DatabaseDao.kt` | Three `suspend` queries: `albumCreditedArtists(albumId)`, `albumPerformerTracks(albumId)` and `albumSongCount(albumId)`. Added next to the existing `albumIndex` hook. |
| `app/src/main/kotlin/com/music/vivi/ui/screens/settings/LocalDownloadSettings.kt` | The folder dialog's preview resolves the same artist value for its sample song, so the preview shows the path that will actually be written, plus one informational line about what `%artist%` resolves to. |
| `app/src/main/res/values/local_download_strings.xml` | One string for that line. |
| `app/build.gradle.kts` | The Kover `includes` filter gains `com.music.vivi.playback.AlbumArtist*` (with the matching test-class exclusion), so the new unit is held to the same 95% line gate as `DownloadFormat`. |
| **NEW** `app/src/test/kotlin/com/music/vivi/playback/AlbumArtistTest.kt` | Unit tests for the rule and its boundaries. |
| `app/src/test/kotlin/com/music/vivi/playback/DownloadFormatTest.kt` | New cases for `folderArtists` in both templates and for `usesArtistToken`. |

Upstream contact grows by the three `DatabaseDao.kt` queries (about twelve added lines) and nothing else.
Every other file in the table is either created by patch 01 or is the patch's own test and Gradle wiring.

### The rule

`folderArtists` receives the credited artist names, the performer rows and the album's song count, and
returns the folder artist list, or `null` when the library knows nothing better than the track artists.

1. Normalise both sides: trim each name, compare case-insensitively.
2. Collapse the performer rows by normalised name, summing `tracks` - one artist can be stored twice with
   different ids.
3. **Rule A** - credited artists are present, at least one performer row exists, and no credited artist is
   among the performers: return `[Various Artists]`.
4. Otherwise, if credited artists are present: return them de-duplicated, in their stored order, with the
   original spelling.
5. **Rule B** - no credited artists, at least two performers, and `topTracks * 2 < albumSongCount`: return
   `[Various Artists]`.
6. Otherwise: return `null`.

Worked examples, all of them covered by tests:

| Album | credited | performers | album songs | verdict |
| --- | --- | --- | --- | --- |
| Metallica, 11 tracks, one guest | Metallica | Metallica 11 | 11 | not a compilation, folder `Metallica` |
| QUEENDOM2 FINAL, 6 tracks / 6 artists | Various Artists (or its localised form) | six artists, one track each | 6 | Rule A, folder `Various Artists` |
| The same album, credits never stored | none | six artists, one track each | 6 | Rule B, folder `Various Artists` |
| 3-track single, artist A on two tracks | none | A 2, B 1 | 3 | Rule B fails (4 < 3 is false), folder `A` |
| Split album credited to A and B, each on half | A, B | A 5, B 5 | 10 | not a compilation, folder `A, B` |
| Score credited to a composer, played by one orchestra | the composer | the orchestra on 12 | 12 | Rule A, folder `Various Artists` |
| Album with credits but no artist rows | Metallica | none | 11 | not a compilation, folder `Metallica` |
| Download straight from search | no album row | n/a | n/a | `null`, folder uses the track artist |

### Data flow

Export stays on its existing path:

`STATE_COMPLETED` -> `DownloadFolderExporter.export(songId)` -> `exportMutex` -> song and format from the
database -> `albumFolderArtists` when the folder template uses `%artist%` -> `DownloadFormat.Input` ->
`DownloadFormat.expand` / `fileName` -> the three writers.

`albumFolderArtists` and its call site in the exporter:

- returns `null` without touching the database when the folder template has no `%artist%` token;
- returns `null` when the song has no album id;
- otherwise reads the credited artists, the performer rows and the album song count, and returns
  `AlbumArtist.folderArtists(...)`;
- wraps all of it in the `albumPosition` pattern: rethrow `CancellationException`, log anything else and
  return `null`, so a failure means today's behaviour rather than a failed export.

`DownloadFormat` then resolves the folder's `%artist%` from `folderArtists ?: artists` and lets the result
flow through the existing `sanitizeSegment`, so invalid characters, the 240-byte cap, whitespace collapse,
the dots-only rule and every traversal guarantee apply to the new value with no new code. The file-name
branch keeps using `artists`. A `folderArtists` list that is empty or only blank names is treated as
absent and the track artists are used, so no caller can force `Unknown Artist` by passing an empty list.

Settings: the folder-format dialog's `LaunchedEffect` already reads the most recently downloaded song for
its preview; it resolves that song's folder artist with the same helper and stores it beside the sample
track number, so the preview line and the exporter cannot disagree. The dialog gains one informational line
naming what `%artist%` resolves to in a folder template.

### Error handling and security

Nothing new is user input, so the security surface is unchanged: the new value is a database string that
becomes a folder segment only through the existing sanitiser, and the constant is ASCII. Every new read is
best-effort inside the exporter's existing `try`, so a locked database, a cancelled export or a stale row
degrades to the track-artist path and never to a wrong folder or a lost download. The Media3 cache is still
never modified.

## Testing

`AlbumArtistTest` (pure JVM, no Android):

- the credited case: disjoint credited artists with performers -> `Various Artists`
- the vacuous case: credited artists but no performer rows -> the credited artists, not a compilation
- credited artists all performing -> the credited artists, in order
- a split credit where one artist performs and one does not -> the credited artists, not a compilation
- the uncredited case: six performers on six songs -> `Various Artists`
- the boundary: the top performer on exactly half -> not a compilation
- a single performer -> not a compilation; no performers at all -> `null`
- duplicate credited names and duplicate performer rows for one name -> de-duplicated and summed
- trimming and case-insensitive comparison on both sides
- a blank credited name is ignored; the returned credited list keeps the stored spelling

`DownloadFormatTest` additions:

- the folder template prefers `folderArtists` when it is present
- the file-name template ignores `folderArtists` and keeps using the track artists
- an absent, empty or all-blank `folderArtists` falls back to the track artists, and a blank track artist
  list still ends at `Unknown Artist`
- `cleaned()` applies the tidy pass to `folderArtists` as it does to `artists`
- `usesArtistToken` accepts `%artist%` and `%Artist%`, and rejects `%album%`-only and token-free templates

The Kover scope gains `AlbumArtist*`, so the new unit is measured by the same gate as `DownloadFormat`.
The three DAO queries are Android-facing and stay outside the gate's scope, alongside the exporter.

On-device checks, added to the existing checklist:

- download a various-artists album under both a picked SAF folder and `Music/Vivi`: one folder per album,
  named `Various Artists`
- download a normal album: unchanged path, and a second download by the same artist reuses the folder
- download an album that has a guest verse on one track: still filed under the main artist
- download a track straight from search: unchanged behaviour
- open the download-format dialog: the preview line shows the new path for the sample song

## Out of scope

- Any change to `%album%`. The album token already prefers the album row's title, so it is uniform whenever
  a detection can happen at all.
- Reorganising, moving or deleting files that already exist.
- New preferences, switches or a user-editable name for the compilation folder.
- Persisting YouTube Music's own various-artists flag (an `AlbumEntity` column plus a Room migration).
- A `%albumartist%` token, and any change to `%artist%` inside the file-name template.
- Songs that have no album row, which keep today's behaviour.

## Acceptance criteria

1. A download from a various-artists album whose credited artists are stored lands in
   `<root>/Various Artists/<album>/`, with the file name still starting with the track's own artist.
2. A download from the same album with no stored credits is detected by the performer-spread rule when at
   least two performers are spread over the album and no performer owns half of it.
3. A normal album, an album with a guest on one track, and a download taken straight from search keep
   exactly today's folder.
4. The compilation folder is always the literal `Various Artists`, whatever the app language.
5. The file-name template's `%artist%` still resolves to the track's artists.
6. Every folder segment still passes the existing character, byte-budget and traversal rules; no new way to
   escape the chosen root is introduced.
7. A failing album-artist lookup logs and falls back to the track artist; `export()` still never throws.
8. `AlbumArtistTest` and `DownloadFormatTest` pass in CI, and the Kover gate still passes with
   `AlbumArtist*` included in its scope.
9. The patch still applies cleanly to pristine upstream `main`, and adds nothing to upstream file bodies
   beyond the existing hooks, the three `DatabaseDao.kt` queries and the one Kover filter line in
   `app/build.gradle.kts`; the weekly `Upstream Drift Check` stays green.

## Delivery

This extends `local-patches/01-download-folder.patch` rather than becoming a second patch: it changes files
that patch 01 creates, so a separate `02` patch would depend on patch 01's exact content and would break
more easily on rebase. The patch is regenerated from a branch off `main`
(`git diff main..<branch> -- app/`), pushed to `binhex/vivi-music`, and rebuilt by the `Local Patch Build`
workflow, so the fork keeps its zero-upstream-edit property.

`local-patches/README.md` gains the behaviour under "What patch 01 does" and the two consequences listed
above under "Known limitations": a credit that performs nothing becomes `Various Artists`, and a two-track
release by two artists is not detected. Generating the patch for the `app/` tree only is what keeps this
design document, and the branch's process notes, out of upstream's source tree.
