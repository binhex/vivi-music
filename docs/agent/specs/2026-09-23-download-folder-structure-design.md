# Templated download folder structure - design

Date: 2026-09-23
Status: approved (pending implementation)
Extends: `local-patches/01-download-folder.patch` (see Delivery)

## Goal

Let the user describe the subfolder structure that completed downloads are written into, relative to the
root they already choose today. With the root set to a picked `Downloads` folder and the structure set to
`%artist%/%album%`, a track lands in `Downloads/Metallica/Master Of Puppets/`.

## Context

Findings from exploring the current code that shape the design:

- The library has **no genre data**. `genre` exists only in `RecognitionHistory` (audio recognition) and in
  the Moods & Genres *browse* screens, which are YouTube Music browse categories rather than per-song
  metadata. No song, album or artist entity has a genre column.
- Artist and album metadata exists (`Song.artists`, `Song.album`, `SongEntity.albumName`/`albumId`) but only
  when the song was inserted by a metadata-aware path: library sync, album/artist/playlist browsing, or an
  imported playlist. `DownloadUtil` itself inserts a bare `SongEntity` (title, duration, thumbnail) plus a
  `FormatEntity`, so a song downloaded straight from a search result has no artist or album at export time.
- The download request carries only the title (`DownloadRequest.setData(song.song.title.toByteArray())`), so
  at export time the only inputs are the song id and the database.
- `SongEntity` has no track number, so no `%track%` token is possible.
- `FormatEntity.bitrate` is available and is already read for the mime type.
- A text-input dialog already exists (`ActionPromptDialog`, `ui/component/Dialog.kt`), `AssistChip` and
  `OutlinedTextField` are already used in the app, and `StorageSettings` already has `LocalDatabase.current`.
- The app module has no test source set at all; junit 4.13.2 is in the version catalog but is not wired up.

## Decisions

| Decision | Choice | Rationale |
| --- | --- | --- |
| `%genre%` | Not supported | No data source exists in the library; the token would be permanently misleading or would need a per-export network lookup. |
| Token set | `%artist%`, `%album%`, `%year%`, `%title%`, `%songId%`, `%quality%` | Every one of them is resolvable from the database and the format row with no network access. |
| Unresolvable token | Fixed placeholder (`Unknown Artist`, `Unknown Album`, `Unknown Year`, `Unknown Quality`) | Predictable path depth, matches the existing `Unknown Artist - Title.m4a` file-name fallback, and makes missing metadata visible. |
| Placeholders localised? | No | Folder names must not change when the user changes app language. |
| Which roots | Both: the picked SAF folder and the built-in `Music/Vivi` destination, with the structure as a subpath under either | The root is a separate choice from the structure; applying it to only one root would be surprising. |
| Default template | `%artist%/%album%` | A root folder full of loose tracks is a bad first impression; organising by artist and album is what almost everyone wants, and the field stays fully editable, including clearing it back to flat. |
| Unset versus empty | An unset preference resolves to the default; an explicitly cleared field means flat | With a non-empty default these must be distinguishable, otherwise opting out would be impossible. The preference is read as `dataStore[key] ?: DEFAULT_TEMPLATE`, so a stored empty string still means flat. |
| Existing installs | New exports are organised; files already written are left alone | Nothing is moved or deleted, and the change is visible only in where the next download lands. Reorganising existing files stays out of scope. |
| Editor | Dialog with a text field, tappable token chips, live preview, inline validation | Discoverability (no need to remember token syntax) plus a visible result before saving. |
| Expansion location | One pure `FolderTemplate` unit; each writer handles only its own path | Sanitising and traversal safety exist once and are unit-testable; the writers stay simple. |
| SAF directories | Walk segment by segment from the tree root, reusing or creating each one | `DocumentsContract.createDocument` creates a single child and a document name cannot contain `/`, so a whole path cannot be created in one call. |
| Unit tests | Added, with `testImplementation(libs.junit)` | The sanitising and traversal rules are the risky part and are pure logic; the repo has no test source set yet. |

## Design

### Units and footprint

| File | Change |
| --- | --- |
| **NEW** `app/src/main/kotlin/com/music/vivi/playback/FolderTemplate.kt` | `parse(template): ParseResult` for validation, `templateOrDefault(stored)` for the unset-versus-emptied rule, `expand(input, template): List<String>` for resolution and sanitising, `fileNameBase(input)`/`fileName(input, mimeType)` for the file name, plus `DEFAULT_TEMPLATE` (`%artist%/%album%`), the token table and per-segment sanitising. Pure Kotlin: no Android imports, so it runs as a JVM unit test, and `Input` carries both album-name and both year candidates so the precedence rules are tested here too. |
| `app/src/main/kotlin/com/music/vivi/playback/LocalDownloadPrefs.kt` | `DownloadFolderTemplateKey = stringPreferencesKey("downloadFolderTemplate")`. |
| `app/src/main/kotlin/com/music/vivi/playback/SafFolders.kt` | `findOrCreateDirectory(context, treeUri, name): Uri?`, built from the existing `findFile`/`createFile` primitives. |
| `app/src/main/kotlin/com/music/vivi/playback/DownloadFolderExporter.kt` | Resolve segments once per export and hand them to the three writers; MediaStore joins them into `RELATIVE_PATH`, SAF walks them, the app-specific directory gets one `mkdirs()`. |
| `app/src/main/kotlin/com/music/vivi/ui/screens/settings/LocalDownloadSettings.kt` | A "Folder structure" row plus the editor dialog (field, chips, preview, validation). |
| `app/src/main/res/values/local_download_strings.xml` | Strings for the new row, dialog, chips, preview and validation errors. |
| **NEW** `app/src/test/kotlin/com/music/vivi/playback/FolderTemplateTest.kt` | Unit tests for parsing, resolution and sanitising. |
| `app/build.gradle.kts` | `testImplementation(libs.junit)`, the Kover plugin declaration, and the `kover {}` block that enforces the 95% line gate over `FolderTemplate`. |

Upstream contact stays at the four lines this patch series already adds in `DownloadUtil.kt` (constructor
parameter plus one call in the `STATE_COMPLETED` branch) and `StorageSettings.kt` (one call to
`LocalDownloadSettingsGroup()`), plus the Kover wiring in `app/build.gradle.kts` (the plugin declaration,
the gate block, and `testImplementation(libs.junit)`): 30 added lines in three upstream files in total.

### Template grammar

- Tokens are written `%name%` and matched case-insensitively (`%Artist%` equals `%artist%`).
- `/` separates segments. `\` is normalised to `/` first, so a Windows-style path still works.
- Empty segments, leading separators and trailing separators are ignored, so `/%artist%//%album%/` is the
  same as `%artist%/%album%`.
- Whitespace around a segment is trimmed.
- At most 6 segments are used; deeper templates are clamped and a warning is logged.
- Each segment is capped at 200 UTF-8 bytes, using the same byte-safe truncation as the file name.
- An unknown token is a validation error in the editor (the dialog names the offending token). If one is
  ever present in the stored value, for example after a hand-edited preference, it is kept as literal text.
- An unset template resolves to `%artist%/%album%`. An explicitly empty template yields no segments, which
  reproduces the flat layout, so clearing the field is a valid way to opt out.

### Token resolution

| Token | Source | When missing |
| --- | --- | --- |
| `%artist%` | `song.artists` joined with `", "` | `Unknown Artist` |
| `%album%` | `song.album?.title`, else `song.song.albumName` | `Unknown Album` |
| `%year%` | `song.song.year`, else `song.album?.year` | `Unknown Year` |
| `%title%` | `song.song.title` | the song id, or `Unknown Title` when even the id sanitises away |
| `%songId%` | `song.song.id` | never missing |
| `%quality%` | `format.bitrate / 1000` followed by `kbps` | `Unknown Quality` (also when the bitrate is not positive) |

Per-segment sanitising, reusing the file-name rules: characters in `\ / : * ? " < > |` become `_`,
whitespace runs collapse to a single space, the segment is trimmed, and trailing dots and spaces are
stripped (they are invalid on FAT/exFAT and on some SAF providers). A segment that ends up empty, or that
consists only of dots, is dropped. The dot rule is what makes `..` impossible as a segment.

### Data flow

Export, on the existing path (`STATE_COMPLETED` -> `DownloadFolderExporter.export` -> mutex -> song and
format from the database -> `FolderTemplate.expand` -> segments):

- **SAF root:** starting at the tree root, walk the segments in order. For each one, look up a child
  directory with that display name and create it with `MIME_TYPE_DIR` when it is missing. A child that
exists but is not a directory (a file happens to use that name) stops the walk: the file is then written in
the last directory that resolved, and the mismatch is logged, rather than creating a `Name (1)` directory
  next to it. The leaf directory becomes the parent for the existing staged write (`.part` file, then delete
  the previous file, then `renameDocument`).
- **MediaStore root (API 29+):** `RELATIVE_PATH = "Music/Vivi"` plus the joined segments. MediaStore creates
  the directories itself, so no directory code runs here. The owner-filtered cleanup and the `IS_PENDING`
  publish flow are unchanged, and because the cleanup recomputes the same relative path, a re-download
  replaces the file in the new location.
- **App-specific directory (API 26-28):** one `mkdirs()` for `File(root, segments.joinToString("/"))`, then
  the existing staged rename.

Settings: the row shows the resolved template, or "Flat" when the field has been cleared. Because the
preference is read as `dataStore[key] ?: DEFAULT_TEMPLATE`, an install that has never touched the setting
shows and uses `%artist%/%album%`, while a deliberately emptied field stays flat. The dialog previews the
resolved path using the most recently downloaded song
(`database.downloadedSongsByCreateDateAsc().first().lastOrNull()`), and falls back to example values when the
library has no downloads.

### Error handling and security

The template is user input that becomes a filesystem path, so the sanitising rules above are
security-relevant, not cosmetic: `/` and `\` are stripped, and a dots-only segment is dropped, so `..` can
never appear as a segment in any of the three writers. MediaStore additionally validates `RELATIVE_PATH`
itself, and the `File`-based writer never joins an unsanitised segment.

A failed SAF walk (revoked grant, folder turned read-only, provider error) throws inside the SAF branch and
is handled by the existing fallback: log, then write to `Music/Vivi` with the same template applied. Depth
and length overruns are clamped and logged rather than fatal. The export contract is unchanged: `export()`
never throws, and the cached download is never modified, so a failure can never affect offline playback.

### Settings editor

The dialog contains the template field, one chip per supported token that inserts the token at the cursor,
a preview line showing the resolved path, inline validation errors, and Reset/Cancel/Save actions. Save is
rejected while the template is invalid, so an unusable value cannot be stored from the UI. Reset restores
`DEFAULT_TEMPLATE` (matching how the other settings dialogs reset to their default); clearing the field and
saving is what produces the flat layout.

## Testing

Unit tests (`FolderTemplateTest`) cover:

- token resolution for every token, including multi-artist joining and each fallback
- sanitising: invalid characters, whitespace collapsing, trailing dots and spaces, empty and dots-only
  segments
- traversal attempts: `..`, `../..`, `/etc`, `a\b`, mixed separators
- the 6-segment cap and the 200-byte segment cap
- case-insensitive token matching, backslash separators, empty template

They run in CI, which executes `:app:testUniversalFossDebugUnitTest` and then `koverXmlReport` +
`koverVerify` (the 95% line gate for the scope above), alongside `assembleUniversalFossDebug` and lint.
`assembleUniversalFossDebug` and lint steps.

On-device checks, added to the existing checklist:

- set `%artist%/%album%`, download a song, confirm the nested folders under both the SAF root and `Music/Vivi`
- confirm a SAF folder gets the nested directories created, and that a second song by the same artist reuses
  them
- re-download a song: the file must be replaced in place, not duplicated
- a song with no artist/album metadata lands in `Unknown Artist/Unknown Album`
- clear the template field and confirm files go flat again, then Reset and confirm the default returns
- a song whose title sanitises to dots only still lands inside the root

## Out of scope

- File-name templating; files stay `Artist - Title.ext`
- `%genre%` and any network metadata lookup
- Retro-exporting, reorganising or moving files that already exist
- Cleaning up files left at the old path after the template changes
- Per-playlist, per-quality or per-source roots

## Acceptance criteria

1. A template of `%artist%/%album%` writes `Downloads/Metallica/Master Of Puppets/<file>` under a picked SAF
   folder and `Music/Vivi/Metallica/Master Of Puppets/<file>` under the default destination.
2. An install that has never set the preference uses `%artist%/%album%`; an explicitly cleared template
   writes flat files directly into the root.
3. Every supported token resolves as specified, with the documented placeholder when data is missing.
4. A template can never place a file outside the chosen root: `..`, absolute paths and mixed separators are
   neutralised, and unit tests prove it.
5. Unknown tokens are rejected in the editor with a message naming the token.
6. Re-downloading a song replaces its file rather than duplicating it.
7. `FolderTemplateTest` passes in CI, and the patch still applies cleanly to pristine upstream `main` and
   still adds only the existing four hook lines plus the Kover wiring (plugin declaration, gate block and
   `testImplementation`) to upstream files.

## Delivery

This extends `local-patches/01-download-folder.patch` rather than becoming a second patch: it changes files
that patch 01 creates, so a separate `02` patch would depend on patch 01's exact content and would break
more easily on rebase. The patch is regenerated from the `local/download-folder` branch, pushed to
`binhex/vivi-music`, and rebuilt by the `Local Patch Build` workflow; the fork keeps its zero-upstream-edit
property, and the weekly `Upstream Drift Check` continues to guard patch applicability.

The patch is generated for the `app/` tree only (`git diff main..local/download-folder -- app/`), so this
design document and other process notes stay in the repository without being pushed into upstream's source
tree by the patch. The fork README records the same command.
