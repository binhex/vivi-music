# Download file format (track numbers and a file-name template) - design

Date: 2026-09-24
Status: approved (pending implementation)
Extends: `local-patches/01-download-folder.patch` (the folder-structure feature released as `v6.0.7-local`)

## Goal

Let the user control the *file name* of an exported download the same way they already control the
folder path, and make album order visible in that name. The default becomes
`%artist% - %album% - %tracknumber% - %title%`, so an album download lands as
`Metallica - Master Of Puppets - 10 - Battery.webm` and sorts correctly in any file manager.

## Context

Findings from exploring the code that shape the design:

- There is **no track-number column** on `SongEntity` or `AlbumEntity`, and no disc-number data
  anywhere in the schema.
- `song_album_map.index` does exist and is exactly the album position: both insert paths populate it
  with `mapIndexed { index, song -> SongAlbumMap(..., index = index) }` over the album page's track
  list (`DatabaseDao.kt` lines ~1421 and ~1541). It is 0-based, so the displayed number is
  `index + 1`.
- The `Song` wrapper (`@Embedded song`, `@Relation artists/album/format`) does **not** expose that
  index, and no existing DAO query returns it for a single song.
- The index only exists for songs inserted from an album page. `DownloadUtil` inserts a **bare
  `SongEntity`** (title, duration, thumbnail) when a row is missing, which is why a download taken
  straight from search or a playlist shows `Unknown Artist` / `Unknown Album` and has no position.
- The file name is still hard-coded in `FolderTemplate.fileNameBase` as `"$artist - $title"`, with
  `MAX_FILE_NAME_BYTES = 200` and `MAX_EXTENSION_BYTES = 5`.
- The token machinery already exists and is fully unit-tested: `parse`, `templateOrDefault`,
  `expand`, `sanitizeSegment`, `truncateToBytes`, `extensionFor`, the `Input` carrier, and the fixed
  fallbacks (`Unknown Artist`, `Unknown Album`, `Unknown Year`, `Unknown Quality`, `Unknown Title`).
- UI precedent to reuse: `FolderStructureDialog` (token chips, live preview, validation, Reset) built
  on `ActionPromptDialog`.
- `DatabaseDao.kt` is the lowest-churn upstream file in this repository (0 commits in 3 months), which
  makes a two-line query addition there the cheapest possible upstream contact.

## Decisions

| Decision | Choice | Rationale |
| --- | --- | --- |
| Track-number source | `song_album_map.index + 1` from the library | Already stored, no network call, no schema migration. The alternatives are worse: fetching at export time adds a request and a new failure mode, and computing the position from the album's songs relies on DB row order because the existing query has no `ORDER BY` on the index. |
| Denormalising the index | Rejected | Would need a Room schema migration, which this patch deliberately avoids. |
| Missing track number | The token resolves to nothing and its part is dropped | A fake number is worse than no number. `Unknown Track` puts a non-value in a name other tools may parse; `00` reads as a real track number. |
| Default file format | `%artist% - %album% - %tracknumber% - %title%` | The user's own format; self-describing even when a file is moved out of its album folder. |
| Budgets | Raised from 200 to **240 bytes** (file name and folder segment) | 200 was a self-imposed margin. The hard limit is 255 bytes per name (ext4/f2fs, MediaStore, most SAF providers); 240 keeps 15 bytes of headroom and still fits the `.part` staging suffix (`Name.m4a.part`, +5 bytes). |
| Overflow handling | Middle elision with an ASCII `...` | Tail truncation cuts the end of `%title%`, and the track name must never be lost. Keeping the start and the end preserves both the leading fields and the track name's tail. |
| Clean-up scope | Conservative: trailing bracket groups from a fixed list, plus a trailing `- Topic` suffix on artists | Removes video cruft without ever touching real title text, so two genuine versions of a track (`(Remastered)`, `(Live)`) never collapse into one name. |
| Clean-up control | A switch inside the File Format dialog, default **on** | Cleaning should be visible and reversible, not silent. |
| Unit shape | Rename `FolderTemplate` to `DownloadFormat` and extend it | One token grammar, one sanitiser, one validation path, and the name matches the UI's "Download Format" section. A second unit would duplicate the token table, sanitiser, byte truncation and fallback rules. |
| Settings structure | A new **Download Format** group containing the **moved** Folder Format row and the new File Format row | One place answers "what will my downloads look like on disk". The Download Folder group keeps only the enable switch, the folder picker and the reset. |
| Patch shape | Extend patch 01 rather than add patch 02 | It changes files that patch 01 creates, so a second patch would depend on patch 01's exact content. |

## Design

### Units and footprint

| File | Change |
| --- | --- |
| `app/src/main/kotlin/com/music/vivi/playback/FolderTemplate.kt` | **Renamed** to `DownloadFormat.kt`, `object FolderTemplate` to `object DownloadFormat`. Owns one token grammar, the existing folder `expand(input, template)`, and a new `fileName(input, mimeType)` replacing the hard-coded `"$artist - $title"`. |
| `app/src/main/kotlin/com/music/vivi/playback/DownloadFolderExporter.kt` | Reads the file-format preference and the clean-up switch, fetches the track number, passes it through `Input`, and calls `DownloadFormat.fileName`. Destinations, staging and rename logic unchanged. |
| `app/src/main/kotlin/com/music/vivi/db/DatabaseDao.kt` | **+2 lines**: a suspend query returning `song_album_map.index` for a song id. |
| `app/src/main/kotlin/com/music/vivi/playback/LocalDownloadPrefs.kt` | +2 keys: file format (string), clean-up toggle (boolean). |
| `app/src/main/kotlin/com/music/vivi/ui/screens/settings/LocalDownloadSettings.kt` | New Download Format group holding the moved Folder Format row and the new File Format row, plus the File Format dialog. |
| `app/src/main/res/values/local_download_strings.xml` | ~10 new strings: group title, the two row titles, dialog title/labels, clean-up label and description, validation copy reuse. |
| `app/src/test/kotlin/com/music/vivi/playback/FolderTemplateTest.kt` | **Renamed** to `DownloadFormatTest.kt`; the 45 existing tests plus ~15 new ones. |
| `app/build.gradle.kts` | One changed line: the Kover include pattern follows the rename (`com.music.vivi.playback.DownloadFormat*`). |

Upstream contact for this change stays at exactly one new query in `DatabaseDao.kt` (2 lines). Everything
else is our own files, plus the already-counted Kover wiring.

### Grammar and tokens

One token set serves both templates, so the editor's chips and validation are identical:
`%artist%`, `%album%`, `%year%`, `%title%`, `%songId%`, `%quality%` and **`%tracknumber%`**.

- Matching stays case-insensitive; `%artist%` and `%Artist%` are the same token.
- Unknown tokens are rejected by the editor, and an unsupported token in a stored value is kept
  literally (both behaviours already exist and are tested).
- The file-name template is free text: tokens plus literal separators.
- A cleared file-format field means the built-in default. An empty file name is never written.

### Missing values and the tidy pass

A token that resolves to nothing must not leave a dangling separator behind. The composition order is:

1. substitute every token (a missing value becomes an empty string),
2. drop parts that are empty after substitution,
3. tidy: collapse and trim separator artefacts - runs of spaces, `-`, `–`, `.`, `,`, `_` - so
   `A - B -  - C` becomes `A - B - C` and a leading or trailing separator disappears,
4. sanitise as today (illegal characters to `_`, control characters removed, whitespace collapsed,
   empty or dots-only parts dropped, trailing dots and spaces stripped),
5. dot-leading guard, byte budget, extension.

Resulting names for the default template:

```text
track number known        Metallica - Master Of Puppets - 10 - Battery.webm
no album row              Metallica - Master Of Puppets - Battery.webm
no album and no artist    Metallica - Battery.webm
```

Documented limitation: an exotic template whose separator is not in the tidy set (for example
`%tracknumber%. %title%`) can leave a stray punctuation character when that token is empty. The
preview in the dialog shows the real result, so the user sees it before saving.

### Track numbers

- Source: `song_album_map.index + 1`, fetched by one new suspend DAO query.
- Padding: two digits (`01`…`99`), raw above 99, so lexical sorting matches track order.
- Absent: no album row or no map row means the token resolves to nothing and its part disappears.
- Failure: a throwing lookup is logged and treated as absent; it never fails the export.
- No `%disc%` token exists, because no disc data exists anywhere in the schema. Recorded as a
  limitation rather than guessed.

### Clean-up rules

Applied to metadata values before substitution, so `%artist%`, `%album%` and `%title%` agree wherever
they are used, including folder templates. Repeat until stable.

- A **trailing bracket group** whose content matches, case-insensitively: `official video`,
  `official music video`, `official audio`, `lyric video`, `lyrics video`, `visualiser`,
  `visualizer`, `audio`, `hd`, `4k`, `mv`.
- A trailing `- Topic` suffix on an artist name (the YouTube auto-generated artist channel suffix,
  preceded by a space).

Nothing inside the real title text is touched. Unlisted tags - `(Remastered)`, `(Live)`,
`(Deluxe Edition)`, `(feat. ...)` - are deliberately preserved, because removing them would make two
genuinely different versions of a track map to one file name.

```text
Battery (Official Video)      -> Battery
One [HD]                      -> One
Metallica - Topic             -> Metallica
Master Of Puppets (Remastered)-> unchanged
Nothing Else Matters (Live)   -> unchanged
```

### Data flow

`exportLocked` reads `DownloadFormatFileKey` (empty means the built-in default) and the clean-up
boolean, fetches the album index, builds `Input` - which gains `trackNumber: Int?` and carries cleaned
metadata when the switch is on - then calls `DownloadFormat.fileName(input, mimeType)`. The write path,
all three destinations, the staged `.part` replacement and the never-throw contract are unchanged. The
folder template keeps using `expand` with the same cleaned metadata, so folders and file names agree.
Nothing is retroactive: existing files are not renamed.

### Error handling, budgets and safety

- The track-number fetch sits inside the existing `try`, so the never-throw and
  never-touch-the-cache contracts still hold.
- Traversal safety is unchanged: the file name is a single path component built by the same sanitiser,
  so no separator, dot-run or control character can survive it.
- Budgets rise from 200 to 240 bytes for the file name and for each folder segment: 15 bytes of
  headroom under the 255-byte filesystem limit, and the staging name still fits.
- A name that still overflows is shortened by middle elision:
  `Metallica - Master Of Puppets - 05 - The Thin...Not Be (Remastered).webm`. The extension and the
  tail of the track name always survive.
- Duplicate-name collisions keep their current, documented semantics; track numbers incidentally make
  them rarer.

### Settings UI

```text
Settings -> Storage

 DOWNLOAD FOLDER
   [x] Save downloads to a folder        (switch)
       Folder: Music/Vivi
       Choose folder
       Use the default folder

 DOWNLOAD FORMAT
   Folder Format   %artist%/%album%                              (moved here, not a copy)
   File Format     %artist% - %album% - %tracknumber% - %title%  (new)
```

The File Format row opens a dialog shaped like the existing folder one: the template field, token
chips, inline validation naming unknown tokens, a live preview of the full resulting path and file
name for a downloaded song (static example values when the library has none), the clean-up switch with
a one-line description, and Reset/Cancel/Save. The Download Format group appears only while the export
feature is enabled, matching the current behaviour of the picker and structure rows.

## Testing

New unit tests, all pure logic and locally verifiable with the existing kotlinc + JUnit harness:

- `%tracknumber%` for 1, 9, 10 and 100 (padding and the raw-over-99 case);
- a missing track number producing exactly `Metallica - Master Of Puppets - Battery.webm` from the
  default template, and `Metallica - Battery.webm` when artist is the only survivor;
- every existing token still resolving, and the new token working in a folder template too;
- each clean-up rule (including case-insensitivity and repetition such as
  `Battery (Official Video) [HD]`), a non-listed tag left untouched, `- Topic`, and the middle of a
  title never being touched;
- clean-up switch off producing verbatim metadata;
- middle elision with an exact expected string and the extension preserved;
- the 240-byte budget for a file name and for a folder segment;
- a cleared file-format template falling back to the built-in default;
- malformed tokens (`%track`) still being flagged.

CI keeps running `assembleUniversalFossDebug`, `testUniversalFossDebugUnitTest` and the Kover 95% line
gate (include updated to `DownloadFormat*`). On-device checklist additions: an album download ordered
correctly in a file manager; a search download with no number; the clean-up switch visibly changing a
name; two long-titled files with the track name intact.

## Out of scope

- Fetching track numbers from the network.
- Renaming or reorganising files that already exist.
- Aggressive title editing (`feat.`, `(Remastered)`, edition tags).
- Embedded tags or artwork, and single-copy storage.
- Disc numbers, and a second unpadded number token.

## Acceptance criteria

1. With the default settings, an album download is written as
   `%artist% - %album% - %tracknumber% - %title%.ext` with a two-digit number taken from the album
   order, and it sorts in album order in a file manager.
2. A song with no album position gets the same name without the number and without a doubled or
   dangling separator.
3. The track name is never lost: it appears in full, or (only when the byte budget forces it) with its
   tail preserved by middle elision.
4. Every supported token resolves as before, `%tracknumber%` is available in both the folder and file
   templates, and unknown or malformed tokens are still rejected by the editor.
5. The clean-up switch, on by default, removes only the listed trailing bracket tags and a trailing
   `- Topic`, and removes nothing else anywhere in a name.
6. Folder and file templates are both editable from Settings -> Storage -> Download Format, with the
   folder row moved rather than duplicated.
7. Unit tests cover every rule above and pass in CI, the Kover gate still passes, and the patch still
   applies cleanly to pristine upstream `main` with upstream contact limited to the existing lines plus
   the new two-line DAO query.

## Delivery

This extends `local-patches/01-download-folder.patch` rather than adding a second patch, for the same
reason as before: it modifies files that patch 01 creates, so a separate patch would depend on patch
01's exact content and break more easily on rebase. The patch is generated for the `app/` tree only
(`git diff main -- app/`), pushed to `binhex/vivi-music`, and rebuilt by `Local Patch Build`; the weekly
`Upstream Drift Check` continues to guard applicability. The design documents themselves stay out of the
patch.
