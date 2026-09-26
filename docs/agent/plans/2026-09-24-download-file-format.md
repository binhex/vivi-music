# Download File Format (track numbers and a file-name template) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use sub-agents (recommended) to implement this plan
> task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the user control the *file name* of an exported download with the same token grammar that
already controls the folder path, so an album download lands as
`Metallica - Master Of Puppets - 10 - Battery.webm` and sorts in album order.

**Architecture:** One pure-Kotlin unit (`DownloadFormat`, renamed from `FolderTemplate`) owns every
naming rule: the token grammar, folder expansion, file-name composition and the metadata tidy pass. The
exporter reads two preferences, looks the album position up with one new DAO query, builds the same
`Input` for both templates and asks `DownloadFormat` for the file name. The settings editor is one
dialog in `LocalDownloadSettings.kt` that drives both templates through the same `parse` the exporter
uses. Nothing outside our own files changes except the two-line DAO query.

**Tech Stack:** Kotlin 2.3.10, Jetpack Compose (Material3), Hilt, Media3 1.7.1, Room, Storage Access
Framework, JUnit 4.13.2, GitHub Actions (fork CI).

**Spec:** `docs/agent/specs/2026-09-24-download-file-format-design.md` (approved). Read it before
starting.

**Scope check:** single subsystem. This extends the existing local-patches feature (one unit, one
exporter, one settings group, one patch file); it introduces no second service, no schema change and no
new delivery mechanism, so it stays one plan. No split needed.

---

## Working environment (read first)

- **Repo:** `/data/clones/clone-vivizzz007-vivi-music`, branch `local/download-folder`. `main` is
  pristine upstream (`6087580f` = `origin/main`). Never commit on `main`.
- **No Android SDK and no JDK 21 in this environment** (only JDK 11). `./gradlew` cannot run here.
  Local verification is the pure-Kotlin harness below; the authoritative verification for anything
  Android (Room, DataStore, Compose, strings) is the fork's CI.
- **Fork:** `binhex/vivi-music`. The fork-side files live in a linked worktree at `/tmp/vivi-fork`
  (branch `fork-main`, checked out there — do not `git switch` to it from the main clone).
- **Upstream contact budget after this change:** exactly four upstream files —
  `DownloadUtil.kt` (constructor parameter + one call), `StorageSettings.kt` (one call to
  `LocalDownloadSettingsGroup()`), `app/build.gradle.kts` (Kover plugin, `testImplementation(libs.junit)`
  and the Kover block, ~30 added lines in total) and the new 3 lines in `DatabaseDao.kt`. Every other
  line belongs to files we own.
- **Never commit:** temp files, `/tmp` scripts, or anything under `docs/agent/` into the patch. The
  patch is generated with the `-- app/` pathspec precisely so specs and plans can never reach upstream.

### Local test harness for the pure unit

Already installed at `/tmp/ktool`. Create the renamed script (a temp file, never committed) as
`/tmp/ktool/run-download-format-tests.sh`:

```bash
#!/usr/bin/env bash
# Compiles DownloadFormat + its test with a standalone Kotlin compiler and runs JUnit directly.
set -euo pipefail

REPO=/data/clones/clone-vivizzz007-vivi-music
TOOL=/tmp/ktool
SRC="$REPO/app/src/main/kotlin/com/music/vivi/playback/DownloadFormat.kt"
TEST="$REPO/app/src/test/kotlin/com/music/vivi/playback/DownloadFormatTest.kt"

rm -rf "$TOOL/out" && mkdir -p "$TOOL/out"

"$TOOL/kotlinc2310/kotlinc/bin/kotlinc" -nowarn \
  -cp "$TOOL/junit.jar:$TOOL/hamcrest.jar" \
  -d "$TOOL/out" "$SRC" "$TEST"

java -cp "$TOOL/out:$TOOL/junit.jar:$TOOL/hamcrest.jar:$TOOL/kotlinc2310/kotlinc/lib/kotlin-stdlib.jar" \
  org.junit.runner.JUnitCore com.music.vivi.playback.DownloadFormatTest
```

Run `chmod +x /tmp/ktool/run-download-format-tests.sh` once. Expected output on success:

```text
JUnit version 4.13.2
............
Time: 0.0xx

OK (N tests)
```

A compile error is the RED signal: kotlinc exits non-zero and prints `error: unresolved reference: ...`.

### The planned unit was dry-run compiled before this plan was published

The Tasks 1-5 result of `DownloadFormat.kt` plus the full 66-test `DownloadFormatTest.kt` were written to
`/tmp/plan-check/` (temp files, outside the repository) and compiled with this exact harness: kotlinc
reports no errors and JUnit reports `OK (66 tests)`. The expected strings in Tasks 3-5 are therefore
measured, not estimated. Two things to keep in mind while implementing:

1. The folder path keeps the existing title fallback (`input.title.orEmpty().ifBlank { input.songId }`) -
   only the file-name path uses the sanitiser-aware chain. Dropping it breaks
   `blank title falls back to the song id`.
2. `/tmp/plan-check/` is a scratch copy for checking the plan. Implementation still happens in
   `app/src/main/...`; never copy those temp files into the repository.

### File map

| Path | Action | Responsibility |
| --- | --- | --- |
| `app/src/main/kotlin/com/music/vivi/playback/FolderTemplate.kt` | **rename** to `DownloadFormat.kt` | One token grammar, folder `expand`, file-name composition, metadata tidy pass. Pure Kotlin, no Android or DB imports. |
| `app/src/test/kotlin/com/music/vivi/playback/FolderTemplateTest.kt` | **rename** to `DownloadFormatTest.kt` | 45 existing tests plus ~20 new ones. |
| `app/src/main/kotlin/com/music/vivi/playback/DownloadFolderExporter.kt` | modify | Read the two new preferences, fetch the album position, clean `Input`, call `DownloadFormat.fileName`. |
| `app/src/main/kotlin/com/music/vivi/db/DatabaseDao.kt` | modify (+3) | One suspend query returning `song_album_map.index` for a song id. |
| `app/src/main/kotlin/com/music/vivi/playback/LocalDownloadPrefs.kt` | modify (+6) | `DownloadFormatFileKey`, `DownloadFormatCleanKey`. |
| `app/src/main/kotlin/com/music/vivi/ui/screens/settings/LocalDownloadSettings.kt` | modify | Split the group in two, move the folder row, add the file row and the shared format dialog. |
| `app/src/main/res/values/local_download_strings.xml` | modify | 6 new strings, 1 removed. |
| `app/build.gradle.kts` | modify (2 lines) | Kover include follows the rename. |
| `local-patches/01-download-folder.patch` *(fork worktree, not in the patch)* | regenerate | The deliverable. |
| `local-patches/README.md` *(fork worktree, not in the patch)* | modify | Feature description, limitations, on-device checklist. |

---

## Task 0: Commit the in-flight folder-template work as the baseline

The working tree already holds the released folder-template feature (patch 01 as published), staged but
uncommitted. Committing it first makes every later task a reviewable diff and makes
`git diff main -- app/` the whole patch again.

**Files:**
- Modify: none (commits what is already in the working tree)

- [ ] **Step 1: Confirm what is staged**

Run: `git status --short`
Expected: `FolderTemplate.kt` and `FolderTemplateTest.kt` as `A`, five `M` app files, two modified
`docs/agent/` files.

- [ ] **Step 2: Confirm nothing outside our footprint is staged**

Run: `git diff --cached --stat`
Expected: only `app/build.gradle.kts`, the five files under `app/src/main/`, and the two docs files.

- [ ] **Step 3: Commit**

```bash
cd /data/clones/clone-vivizzz007-vivi-music
git add -A
git commit -m "local: templated download folder structure"
```

- [ ] **Step 4: Verify the tree is clean and the patch baseline is right**

Run: `git status --short && git diff --stat main -- app/ | tail -3`
Expected: no output from `git status`, and the diff stat lists the app files (this is the patch content).

---

## Task 1: Rename `FolderTemplate` to `DownloadFormat`

Pure rename, no behaviour change. The 45 existing tests are the safety net: they must all still pass
after the rename, which is what makes this a refactor rather than a redesign.

**Files:**
- Rename: `app/src/main/kotlin/com/music/vivi/playback/FolderTemplate.kt` → `DownloadFormat.kt`
- Rename: `app/src/test/kotlin/com/music/vivi/playback/FolderTemplateTest.kt` → `DownloadFormatTest.kt`
- Modify: `app/src/main/kotlin/com/music/vivi/ui/screens/settings/LocalDownloadSettings.kt` (import + 7 call sites)
- Modify: `app/src/main/kotlin/com/music/vivi/playback/DownloadFolderExporter.kt` (7 call sites)
- Modify: `app/build.gradle.kts` (Kover include + exclude)

- [ ] **Step 1: Rename both files with git so the history follows**

```bash
cd /data/clones/clone-vivizzz007-vivi-music
git mv app/src/main/kotlin/com/music/vivi/playback/FolderTemplate.kt \
       app/src/main/kotlin/com/music/vivi/playback/DownloadFormat.kt
git mv app/src/test/kotlin/com/music/vivi/playback/FolderTemplateTest.kt \
       app/src/test/kotlin/com/music/vivi/playback/DownloadFormatTest.kt
```

- [ ] **Step 2: Replace the identifiers**

```bash
cd /data/clones/clone-vivizzz007-vivi-music
sed -i 's/\bFolderTemplate\b/DownloadFormat/g' \
  app/src/main/kotlin/com/music/vivi/playback/DownloadFormat.kt \
  app/src/test/kotlin/com/music/vivi/playback/DownloadFormatTest.kt \
  app/src/main/kotlin/com/music/vivi/playback/DownloadFolderExporter.kt \
  app/src/main/kotlin/com/music/vivi/ui/screens/settings/LocalDownloadSettings.kt \
  app/build.gradle.kts
```

Note: `FolderTemplateTest` matches `\bFolderTemplate\b` only when it is not followed by a word
character, so the test class name needs its own replacement:

```bash
cd /data/clones/clone-vivizzz007-vivi-music
sed -i 's/FolderTemplateTest/DownloadFormatTest/g' \
  app/src/test/kotlin/com/music/vivi/playback/DownloadFormatTest.kt \
  app/build.gradle.kts
```

- [ ] **Step 3: Fix the Kover comment and include path by hand**

In `app/build.gradle.kts` the block must read exactly:

```kotlin
// Coverage gate for the JVM-testable code. The scope is deliberately limited to DownloadFormat, the pure
// path and naming rules: the rest of this patch depends on Android, Hilt, Media3 or Compose and would need
// Robolectric or a device. That excluded debt is recorded in the fork README, not here.
kover {
    reports {
        filters {
            includes {
                classes("com.music.vivi.playback.DownloadFormat*")
            }
            excludes {
                // The wildcard above also matches the test class; test code is fully covered and must not
                // pad the number the gate measures.
                classes("com.music.vivi.playback.DownloadFormatTest")
            }
        }
        verify {
            rule {
                minBound(95)
            }
        }
    }
}
```

- [ ] **Step 4: Update the local harness script for the new names**

```bash
sed -e 's/FolderTemplate/DownloadFormat/g' /tmp/ktool/run-folder-template-tests.sh \
  > /tmp/ktool/run-download-format-tests.sh
chmod +x /tmp/ktool/run-download-format-tests.sh
```

- [ ] **Step 5: Run the harness and confirm the 45 tests still pass**

Run: `/tmp/ktool/run-download-format-tests.sh`
Expected: `OK (45 tests)`

- [ ] **Step 6: Confirm no stale reference is left**

Run: `grep -rn "FolderTemplate" app/ || echo "none"`
Expected: `none`

- [ ] **Step 7: Commit**

```bash
cd /data/clones/clone-vivizzz007-vivi-music
git add -A
git commit -m "local: rename FolderTemplate to DownloadFormat"
```

---

## Task 2: `%tracknumber%` token and `Input.trackNumber`

**Files:**
- Modify: `app/src/main/kotlin/com/music/vivi/playback/DownloadFormat.kt`
- Test: `app/src/test/kotlin/com/music/vivi/playback/DownloadFormatTest.kt`

- [ ] **Step 1: Write the failing tests**

Add to `DownloadFormatTest.kt` inside the class, and add the new helper parameter:

```kotlin
    private fun input(
        songId: String = "dQw4w9WgXcQ",
        title: String? = "Enter Sandman",
        artists: List<String> = listOf("Metallica"),
        albumTitle: String? = "Master Of Puppets",
        storedAlbumName: String? = null,
        songYear: Int? = 1986,
        albumYear: Int? = null,
        bitrate: Int? = 256_000,
        trackNumber: Int? = null,
    ) = DownloadFormat.Input(
        songId = songId,
        title = title,
        artists = artists,
        albumTitle = albumTitle,
        storedAlbumName = storedAlbumName,
        songYear = songYear,
        albumYear = albumYear,
        bitrate = bitrate,
        trackNumber = trackNumber,
    )
```

```kotlin
    @Test
    fun `parse accepts the track number token`() {
        assertTrue(DownloadFormat.parse("%tracknumber% - %title%").isValid)
        assertTrue(DownloadFormat.TOKENS.contains("%tracknumber%"))
    }

    @Test
    fun `track number is two digits up to ninety nine`() {
        assertEquals("01", DownloadFormat.expand(input(trackNumber = 1), "%tracknumber%").single())
        assertEquals("09", DownloadFormat.expand(input(trackNumber = 9), "%tracknumber%").single())
        assertEquals("10", DownloadFormat.expand(input(trackNumber = 10), "%tracknumber%").single())
        assertEquals("99", DownloadFormat.expand(input(trackNumber = 99), "%tracknumber%").single())
    }

    @Test
    fun `track number above ninety nine stays raw`() {
        assertEquals("100", DownloadFormat.expand(input(trackNumber = 100), "%tracknumber%").single())
    }

    @Test
    fun `a missing track number contributes no segment`() {
        assertTrue(DownloadFormat.expand(input(trackNumber = null), "%tracknumber%").isEmpty())
        assertTrue(DownloadFormat.expand(input(trackNumber = 0), "%tracknumber%").isEmpty())
    }
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `/tmp/ktool/run-download-format-tests.sh`
Expected: FAIL - kotlinc reports `error: unresolved reference: trackNumber` (the helper passes a field
`Input` does not have yet). That is the RED signal.

- [ ] **Step 3: Add the field, the token and its resolution**

In `DownloadFormat.kt`, extend `TOKENS` and `SUPPORTED`:

```kotlin
    /** Tokens offered as chips in the editor, in display order. */
    val TOKENS = listOf("%artist%", "%album%", "%year%", "%title%", "%songId%", "%quality%", "%tracknumber%")

    private val SUPPORTED = setOf("artist", "album", "year", "title", "songid", "quality", "tracknumber")
```

Extend `Input` with the new field (last, defaulted, so existing call sites keep compiling):

```kotlin
    data class Input(
        val songId: String,
        val title: String?,
        val artists: List<String>,
        val albumTitle: String?,
        val storedAlbumName: String?,
        val songYear: Int?,
        val albumYear: Int?,
        val bitrate: Int?,
        /** Album position from `song_album_map`, 1-based. Null when the song has no album row. */
        val trackNumber: Int? = null,
    )
```

Add the branch to `resolve` (keep the existing branches untouched):

```kotlin
        "quality" -> input.bitrate?.takeIf { it > 0 }?.let { "${it / 1000}kbps" } ?: UNKNOWN_QUALITY
        "tracknumber" -> trackNumberText(input.trackNumber)
        else -> literal
```

Add the formatter next to `resolve`:

```kotlin
    /**
     * `01`...`99`, raw above 99 so lexical sorting still matches track order, and an empty string when the
     * song has no album position - a part that resolves to nothing is dropped from the name, because a
     * fabricated number (`00`, `Unknown Track`) would be read as a real track number by other tools.
     */
    internal fun trackNumberText(trackNumber: Int?): String = trackNumber
        ?.takeIf { it > 0 }
        ?.let { if (it < 100) it.toString().padStart(2, '0') else it.toString() }
        .orEmpty()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `/tmp/ktool/run-download-format-tests.sh`
Expected: `OK (49 tests)`

- [ ] **Step 5: Commit**

```bash
cd /data/clones/clone-vivizzz007-vivi-music
git add app/src/main/kotlin/com/music/vivi/playback/DownloadFormat.kt \
        app/src/test/kotlin/com/music/vivi/playback/DownloadFormatTest.kt
git commit -m "local: add the %tracknumber% token"
```

---

## Task 3: Compose the file name from a template

This is the behavioural core: the file name stops being `"$artist - $title"` and becomes the resolved
template, with empty parts and their separators dropped.

**Files:**
- Modify: `app/src/main/kotlin/com/music/vivi/playback/DownloadFormat.kt`
- Test: `app/src/test/kotlin/com/music/vivi/playback/DownloadFormatTest.kt`
- Modify call sites so the tree keeps compiling: `DownloadFolderExporter.kt`, `LocalDownloadSettings.kt`

- [ ] **Step 1: Write the failing tests**

Replace the three `templateOrDefault` / file-name tests that lock in the present shape:

```kotlin
    @Test
    fun `templateOrDefault keeps an unset template at the default and an emptied one flat`() {
        assertEquals(DownloadFormat.DEFAULT_FOLDER_TEMPLATE, DownloadFormat.templateOrDefault(null))
        assertEquals("", DownloadFormat.templateOrDefault(""))
        assertEquals("%year%", DownloadFormat.templateOrDefault("%year%"))
    }

    @Test
    fun `file template defaults when unset, emptied or blank`() {
        assertEquals(DownloadFormat.DEFAULT_FILE_TEMPLATE, DownloadFormat.fileTemplateOrDefault(null))
        assertEquals(DownloadFormat.DEFAULT_FILE_TEMPLATE, DownloadFormat.fileTemplateOrDefault(""))
        assertEquals(DownloadFormat.DEFAULT_FILE_TEMPLATE, DownloadFormat.fileTemplateOrDefault("   "))
        assertEquals("%title%", DownloadFormat.fileTemplateOrDefault("%title%"))
    }

    @Test
    fun `default file template writes artist album track and title`() {
        assertEquals(
            "Metallica - Master Of Puppets - 10 - Battery.m4a",
            DownloadFormat.fileName(
                input(title = "Battery", trackNumber = 10),
                DownloadFormat.DEFAULT_FILE_TEMPLATE,
                "audio/mp4",
            ),
        )
    }

    @Test
    fun `a part with no value drops together with its separator`() {
        assertEquals(
            "Metallica - Master Of Puppets - Battery.m4a",
            DownloadFormat.fileName(
                input(title = "Battery", trackNumber = null),
                DownloadFormat.DEFAULT_FILE_TEMPLATE,
                "audio/mp4",
            ),
        )
    }

    @Test
    fun `a missing album and track number leave artist and title only`() {
        assertEquals(
            "Metallica - Battery.m4a",
            DownloadFormat.fileName(
                input(
                    title = "Battery",
                    albumTitle = null,
                    storedAlbumName = null,
                    trackNumber = null,
                ),
                DownloadFormat.DEFAULT_FILE_TEMPLATE,
                "audio/mp4",
            ),
        )
    }

    @Test
    fun `a missing artist does not leave a leading separator`() {
        assertEquals(
            "Master Of Puppets - Battery.m4a",
            DownloadFormat.fileName(
                input(title = "Battery", artists = emptyList(), trackNumber = null),
                DownloadFormat.DEFAULT_FILE_TEMPLATE,
                "audio/mp4",
            ),
        )
    }

    @Test
    fun `custom separators and literal text are kept`() {
        assertEquals(
            "Metallica.Enter Sandman.m4a",
            DownloadFormat.fileName(input(), "%artist%.%title%", "audio/mp4"),
        )
        assertEquals(
            "[Metallica] Enter Sandman.m4a",
            DownloadFormat.fileName(input(), "[%artist%] %title%", "audio/mp4"),
        )
    }

    @Test
    fun `an unknown token is kept literally in the file name`() {
        assertEquals(
            "%genre% - Enter Sandman.m4a",
            DownloadFormat.fileName(input(), "%genre% - %title%", "audio/mp4"),
        )
    }

    @Test
    fun `an empty template never produces an empty file name`() {
        assertEquals("dQw4w9WgXcQ.m4a", DownloadFormat.fileName(input(title = null), "", "audio/mp4"))
    }
```

Then replace every file-name test that asserted the old hard-coded shape:

```kotlin
    @Test
    fun `file name follows the default template`() {
        assertEquals(
            "Metallica - Master Of Puppets - Enter Sandman.m4a",
            DownloadFormat.fileName(input(), DownloadFormat.DEFAULT_FILE_TEMPLATE, "audio/mp4"),
        )
    }

    @Test
    fun `file name base carries no extension`() {
        assertEquals(
            "Metallica - Master Of Puppets - Enter Sandman",
            DownloadFormat.fileNameBase(input(), DownloadFormat.DEFAULT_FILE_TEMPLATE),
        )
    }

    @Test
    fun `file name extension follows the mime type`() {
        val base = "Metallica - Master Of Puppets - Enter Sandman"
        assertEquals("$base.webm", DownloadFormat.fileName(input(), DownloadFormat.DEFAULT_FILE_TEMPLATE, "audio/webm; codecs=opus"))
        assertEquals("$base.mp3", DownloadFormat.fileName(input(), DownloadFormat.DEFAULT_FILE_TEMPLATE, "audio/mpeg"))
        assertEquals("$base.ogg", DownloadFormat.fileName(input(), DownloadFormat.DEFAULT_FILE_TEMPLATE, "audio/ogg"))
        assertEquals("$base.opus", DownloadFormat.fileName(input(), DownloadFormat.DEFAULT_FILE_TEMPLATE, "audio/opus"))
        assertEquals("$base.flac", DownloadFormat.fileName(input(), DownloadFormat.DEFAULT_FILE_TEMPLATE, "audio/flac"))
        assertEquals("$base.aac", DownloadFormat.fileName(input(), DownloadFormat.DEFAULT_FILE_TEMPLATE, "audio/aac"))
        assertEquals(".m4a", DownloadFormat.extensionFor("application/x-mpegURL"))
        assertEquals(".mp3", DownloadFormat.extensionFor("audio/mpeg"))
        assertEquals("$base.m4a", DownloadFormat.fileName(input(), DownloadFormat.DEFAULT_FILE_TEMPLATE, null))
    }

    @Test
    fun `file name falls back to the song id for a blank title`() {
        assertEquals(
            "Metallica - Master Of Puppets - dQw4w9WgXcQ.m4a",
            DownloadFormat.fileName(input(title = " "), DownloadFormat.DEFAULT_FILE_TEMPLATE, "audio/mp4"),
        )
    }

    @Test
    fun `file name falls back to the song id when the title is unusable`() {
        assertEquals(
            "Master Of Puppets - dQw4w9WgXcQ.m4a",
            DownloadFormat.fileName(
                input(title = "..", artists = emptyList()),
                DownloadFormat.DEFAULT_FILE_TEMPLATE,
                "audio/mp4",
            ),
        )
    }

    @Test
    fun `file name sanitises an id used as the title fallback`() {
        assertEquals(
            "Master Of Puppets - a_b.m4a",
            DownloadFormat.fileName(
                input(title = "..", artists = emptyList(), songId = "a/b"),
                DownloadFormat.DEFAULT_FILE_TEMPLATE,
                "audio/mp4",
            ),
        )
    }

    @Test
    fun `file name survives an id that sanitises away`() {
        assertEquals(
            "Master Of Puppets - Unknown Title.m4a",
            DownloadFormat.fileName(
                input(title = "..", artists = emptyList(), songId = ".."),
                DownloadFormat.DEFAULT_FILE_TEMPLATE,
                "audio/mp4",
            ),
        )
    }

    @Test
    fun `file name never starts with a dot`() {
        assertEquals(
            "_.38 Special - Master Of Puppets - Enter Sandman",
            DownloadFormat.fileNameBase(
                input(artists = listOf(".38 Special")),
                DownloadFormat.DEFAULT_FILE_TEMPLATE,
            ),
        )
    }
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `/tmp/ktool/run-download-format-tests.sh`
Expected: FAIL - `error: unresolved reference: DEFAULT_FILE_TEMPLATE`, `fileTemplateOrDefault`.

- [ ] **Step 3: Extend `DownloadFormat`**

Rename the folder default and add the file default and its resolver:

```kotlin
    /** Organise downloads by artist and album unless the user says otherwise. */
    const val DEFAULT_FOLDER_TEMPLATE = "%artist%/%album%"

    /** The file-name template used when the preference is unset, emptied or blank. */
    const val DEFAULT_FILE_TEMPLATE = "%artist% - %album% - %tracknumber% - %title%"
```

```kotlin
    /**
     * Resolves the folder preference: an unset value means the default template, while a stored empty
     * string means the user asked for flat output.
     */
    fun templateOrDefault(stored: String?): String = stored ?: DEFAULT_FOLDER_TEMPLATE

    /**
     * Resolves the file-name preference. Unlike the folder template, an emptied value means the built-in
     * default: an export must always have a name, so there is no meaningful "flat file name" state.
     */
    fun fileTemplateOrDefault(stored: String?): String =
        stored?.takeIf { it.isNotBlank() } ?: DEFAULT_FILE_TEMPLATE
```

Add the separator pattern next to the other patterns:

```kotlin
    /**
     * Separator runs the file-name tidy pass collapses and trims. Only the template is scanned with it, so
     * a separator inside a metadata value (`Mr. Robot`, `AC/DC`) is never treated as a template separator.
     */
    private val SEPARATOR_RUN = Regex("[\\s]*[-\\u2013._,]+[\\s]*")
```

Replace `substitute` and `resolve` so that file-name resolution can report an absent value:

```kotlin
    private fun substitute(piece: String, input: Input, forFileName: Boolean = false): String =
        TOKEN_PATTERN.replace(piece) { match ->
            resolve(match.groupValues[1].lowercase(), match.value, input, forFileName)
        }

    /**
     * [literal] is the token exactly as the user wrote it, so an unsupported token keeps its original
     * spelling instead of being folded to lower case.
     *
     * [forFileName] switches two behaviours. A folder must always exist, so an absent value becomes its
     * `Unknown *` fallback and the tree stays predictable. A file name must not invent values, so an
     * absent value becomes empty and its whole part is dropped - except the title, which must never be
     * lost, and so still falls back to the song id.
     */
    private fun resolve(token: String, literal: String, input: Input, forFileName: Boolean): String = when (token) {
        "artist" -> input.artists.joinToString(", ")
            .ifBlank { if (forFileName) "" else UNKNOWN_ARTIST }
        "album" -> (input.albumTitle ?: input.storedAlbumName).orEmpty()
            .ifBlank { if (forFileName) "" else UNKNOWN_ALBUM }
        "year" -> (input.songYear ?: input.albumYear)?.toString()
            ?: if (forFileName) "" else UNKNOWN_YEAR
        "title" -> titleText(input, forFileName)
        "songid" -> input.songId
        "quality" -> input.bitrate?.takeIf { it > 0 }?.let { "${it / 1000}kbps" }
            ?: if (forFileName) "" else UNKNOWN_QUALITY
        "tracknumber" -> trackNumberText(input.trackNumber)
        else -> literal
    }

    /** The title never disappears from a file name; a folder segment is allowed to sanitise away. */
    private fun titleText(input: Input, forFileName: Boolean): String {
        if (!forFileName) return input.title.orEmpty().ifBlank { input.songId }
        return sanitizeSegment(input.title.orEmpty())
            .ifBlank { sanitizeSegment(input.songId) }
            .ifBlank { UNKNOWN_TITLE }
    }
```

Replace `fileNameBase` / `fileName` with the template-driven versions:

```kotlin
    /**
     * Sanitised file name base for [template], without an extension: every token is resolved, a part that
     * resolves to nothing is dropped together with its separator, and the result is sanitised and brought
     * inside the byte budget.
     */
    fun fileNameBase(input: Input, template: String): String {
        val composed = cleanSegment(compose(input, template))
        val base = composed.ifBlank { sanitizeSegment(input.songId).ifBlank { UNKNOWN_TITLE } }
        val budget = MAX_FILE_NAME_BYTES - MAX_EXTENSION_BYTES
        val trimmed = truncateToBytes(base, budget).trimEnd('.', ' ')
        // A dot-leading name is hidden from file managers and from the API 26-28 media scanner.
        return if (trimmed.startsWith('.')) {
            truncateToBytes("_$trimmed", budget).trimEnd('.', ' ')
        } else {
            trimmed
        }
    }

    /** `Artist - Album - 10 - Title.ext`, the name the exporter writes. */
    fun fileName(input: Input, template: String, mimeType: String?): String =
        "${fileNameBase(input, template)}${extensionFor(mimeType)}"

    /**
     * Walks the template as alternating text and separator pieces. Only template separators are ever
     * collapsed, so characters inside a metadata value are untouched. A piece whose tokens all resolve to
     * nothing is dropped, and the separator in front of it goes with it: `A - B -  - C` becomes
     * `A - B - C`, and a leading or trailing separator disappears.
     */
    private fun compose(input: Input, template: String): String {
        val out = StringBuilder()
        var pendingSeparator: String? = null
        var last = 0

        fun addPiece(piece: String) {
            val value = substitute(piece, input, forFileName = true)
            if (value.isBlank()) return
            if (out.isNotEmpty()) pendingSeparator?.let(out::append)
            pendingSeparator = null
            out.append(value)
        }

        SEPARATOR_RUN.findAll(template).forEach { match ->
            addPiece(template.substring(last, match.range.first))
            pendingSeparator = match.value
            last = match.range.last + 1
        }
        addPiece(template.substring(last))
        return out.toString()
    }
```

Split the character rules out of `sanitizeSegment` so the file-name path can sanitise before it
truncates:

```kotlin
    internal fun sanitizeSegment(segment: String, maxBytes: Int = MAX_SEGMENT_BYTES): String {
        val cleaned = cleanSegment(segment)
        if (cleaned.isEmpty()) return ""
        return truncateToBytes(cleaned, maxBytes).trimEnd('.', ' ')
    }

    /**
     * The character rules on their own, with no byte budget: separators and other invalid characters become
     * `_`, whitespace collapses, and a segment that is empty or only dots is dropped - which is what makes
     * `..` impossible as a segment.
     */
    private fun cleanSegment(segment: String): String {
        val cleaned = segment
            .replace(INVALID_CHARS, "_")
            .replace(WHITESPACE, " ")
            .trim()
        if (cleaned.isEmpty() || cleaned.all { it == '.' }) return ""
        return cleaned
    }
```

- [ ] **Step 4: Update the two call sites so the module still compiles**

In `DownloadFolderExporter.kt`, replace the two call lines (the full wiring arrives in Task 6):

```kotlin
            val template = DownloadFormat.templateOrDefault(context.dataStore[DownloadFolderTemplateKey])
            if (DownloadFormat.parse(template).tooDeep) {
                Timber.tag(TAG).w(
                    "Template uses more than %d folders, the extra ones are ignored",
                    DownloadFormat.MAX_SEGMENTS,
                )
            }
            val mimeType = sniffMimeType(songId)
                ?: song.format?.mimeType.orEmpty().substringBefore(';').trim()
                    .ifEmpty { DownloadFormat.DEFAULT_MIME_TYPE }
            val fileName = DownloadFormat.fileName(input, DownloadFormat.DEFAULT_FILE_TEMPLATE, mimeType)
```

In `LocalDownloadSettings.kt`, replace the folder default and the preview call:

```kotlin
    val (template, onTemplateChange) =
        rememberPreference(DownloadFolderTemplateKey, DownloadFormat.DEFAULT_FOLDER_TEMPLATE)
```

```kotlin
    // No extension in the preview: the real one is decided at export time from the cached bytes.
    val previewName = DownloadFormat.fileNameBase(previewInput, DownloadFormat.DEFAULT_FILE_TEMPLATE)
```

and the dialog's reset button:

```kotlin
        onReset = { draft = TextFieldValue(DownloadFormat.DEFAULT_FOLDER_TEMPLATE) },
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `/tmp/ktool/run-download-format-tests.sh`
Expected: `OK (57 tests)` (45 existing, 4 from Task 2, 8 added here)

- [ ] **Step 6: Commit**

```bash
cd /data/clones/clone-vivizzz007-vivi-music
git add -A
git commit -m "local: compose the export file name from a template"
```

---

## Task 4: Raise the budgets to 240 bytes and elide in the middle

**Files:**
- Modify: `app/src/main/kotlin/com/music/vivi/playback/DownloadFormat.kt`
- Test: `app/src/test/kotlin/com/music/vivi/playback/DownloadFormatTest.kt`

- [ ] **Step 1: Write the failing tests**

Replace the three budget tests:

```kotlin
    @Test
    fun `a segment cut to the byte budget never ends in a dot or a space`() {
        val long = "a".repeat(239)
        assertEquals(listOf(long), DownloadFormat.expand(input(artists = listOf("$long .b")), "%artist%"))
        assertEquals(listOf(long), DownloadFormat.expand(input(artists = listOf("$long  b")), "%artist%"))
    }

    @Test
    fun `segments are capped at exactly 240 bytes`() {
        val segment = DownloadFormat.expand(input(artists = listOf("ア".repeat(300))), "%artist%").single()
        assertEquals("ア".repeat(80), segment)
        assertEquals(240, segment.toByteArray(Charsets.UTF_8).size)
    }

    @Test
    fun `truncation stops on a code point boundary`() {
        val segment = DownloadFormat.expand(input(artists = listOf("a" + "😀".repeat(60))), "%artist%").single()
        assertEquals("a" + "😀".repeat(59), segment)
        assertEquals(237, segment.toByteArray(Charsets.UTF_8).size)
    }
```

Replace the file-name budget test and add the elision test:

```kotlin
    @Test
    fun `an overlong name keeps its head, its tail and the extension`() {
        val name = DownloadFormat.fileName(
            input(title = "A".repeat(300), trackNumber = 5),
            DownloadFormat.DEFAULT_FILE_TEMPLATE,
            "audio/mp4",
        )
        assertEquals(
            "Metallica - Master Of Puppets - 05 - " + "A".repeat(79) + "..." + "A".repeat(116) + ".m4a",
            name,
        )
    }

    @Test
    fun `file name stays inside the byte budget`() {
        val name = DownloadFormat.fileName(
            input(artists = listOf("ア".repeat(200))),
            DownloadFormat.DEFAULT_FILE_TEMPLATE,
            "audio/mp4",
        )
        assertTrue(name.toByteArray(Charsets.UTF_8).size <= DownloadFormat.MAX_FILE_NAME_BYTES)
        assertTrue(name.startsWith("ア"))
        assertTrue(name.contains("..."))
        assertTrue(name.endsWith("Enter Sandman.m4a"))
    }
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `/tmp/ktool/run-download-format-tests.sh`
Expected: FAIL - `expected:<...> but was:<...>` for the 200-byte expectations and for the elision
string (the name is still tail-truncated at 200 bytes).

- [ ] **Step 3: Raise the budgets and add middle elision**

```kotlin
    /** Filesystems cap a single name at 255 bytes; 240 leaves 15 bytes of headroom. */
    const val MAX_SEGMENT_BYTES = 240

    /** The same budget applies to a composed file name. */
    const val MAX_FILE_NAME_BYTES = 240

    /** Joins the head and the tail of an elided name. ASCII on purpose: it must survive any provider. */
    private const val MIDDLE_MARKER = "..."
```

Use it from `fileNameBase` (two places: the first truncate and the dot-leading fallback):

```kotlin
        val budget = MAX_FILE_NAME_BYTES - MAX_EXTENSION_BYTES
        val trimmed = elideMiddle(base, budget).trimEnd('.', ' ')
        // A dot-leading name is hidden from file managers and from the API 26-28 media scanner.
        return if (trimmed.startsWith('.')) {
            elideMiddle("_$trimmed", budget).trimEnd('.', ' ')
        } else {
            trimmed
        }
```

Add the two helpers next to `truncateToBytes`:

```kotlin
    /**
     * Shortens an overlong name by keeping both ends and marking the cut. Tail truncation would cut the
     * end of `%title%`, and the track name must never be lost, so the budget is split evenly between the
     * head (which carries the leading fields) and the tail (which carries the track name).
     */
    internal fun elideMiddle(name: String, maxBytes: Int): String {
        if (name.toByteArray(Charsets.UTF_8).size <= maxBytes) return name
        val markerBytes = MIDDLE_MARKER.toByteArray(Charsets.UTF_8).size
        val budget = maxBytes - markerBytes
        if (budget <= 0) return truncateToBytes(name, maxBytes)
        val headBytes = budget / 2
        val tailBytes = budget - headBytes
        return truncateToBytes(name, headBytes) + MIDDLE_MARKER + truncateTailToBytes(name, tailBytes)
    }

    /** The last [maxBytes] bytes of [name], cut on a code point boundary so the result is valid UTF-8. */
    internal fun truncateTailToBytes(name: String, maxBytes: Int): String {
        val bytes = name.toByteArray(Charsets.UTF_8)
        if (bytes.size <= maxBytes) return name
        var start = bytes.size - maxBytes
        while (start < bytes.size && bytes[start].toInt() and 0xC0 == 0x80) start++
        return String(bytes, start, bytes.size - start, Charsets.UTF_8)
    }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `/tmp/ktool/run-download-format-tests.sh`
Expected: `OK (58 tests)` (the elision test is the only addition; the other four assertions are rewrites)

- [ ] **Step 5: Commit**

```bash
cd /data/clones/clone-vivizzz007-vivi-music
git add app/src/main/kotlin/com/music/vivi/playback/DownloadFormat.kt \
        app/src/test/kotlin/com/music/vivi/playback/DownloadFormatTest.kt
git commit -m "local: raise the name budget to 240 bytes with middle elision"
```

---

## Task 5: Metadata clean-up

**Files:**
- Modify: `app/src/main/kotlin/com/music/vivi/playback/DownloadFormat.kt`
- Test: `app/src/test/kotlin/com/music/vivi/playback/DownloadFormatTest.kt`

- [ ] **Step 1: Write the failing tests**

```kotlin
    @Test
    fun `a trailing listed bracket tag is removed`() {
        assertEquals("Battery", DownloadFormat.tidyMetadata("Battery (Official Video)"))
        assertEquals("One", DownloadFormat.tidyMetadata("One [HD]"))
        assertEquals("Battery", DownloadFormat.tidyMetadata("Battery (Official Video) [HD]"))
        assertEquals("One", DownloadFormat.tidyMetadata("One (Official Audio)"))
        assertEquals("One", DownloadFormat.tidyMetadata("One (Lyrics Video)"))
        assertEquals("One", DownloadFormat.tidyMetadata("One [Visualizer]"))
        assertEquals("One", DownloadFormat.tidyMetadata("One (4K)"))
        assertEquals("One", DownloadFormat.tidyMetadata("One [MV]"))
    }

    @Test
    fun `bracket tags are matched case insensitively`() {
        assertEquals("Battery", DownloadFormat.tidyMetadata("Battery (OFFICIAL VIDEO)"))
        assertEquals("Battery", DownloadFormat.tidyMetadata("Battery [hd]"))
    }

    @Test
    fun `a trailing topic suffix is removed`() {
        assertEquals("Metallica", DownloadFormat.tidyMetadata("Metallica - Topic"))
        assertEquals("Metallica", DownloadFormat.tidyMetadata("Metallica - topic"))
        assertEquals("Topics of Life", DownloadFormat.tidyMetadata("Topics of Life"))
    }

    @Test
    fun `edition tags are preserved`() {
        assertEquals("Master Of Puppets (Remastered)", DownloadFormat.tidyMetadata("Master Of Puppets (Remastered)"))
        assertEquals("Nothing Else Matters (Live)", DownloadFormat.tidyMetadata("Nothing Else Matters (Live)"))
        assertEquals("King Nothing (Deluxe Edition)", DownloadFormat.tidyMetadata("King Nothing (Deluxe Edition)"))
        assertEquals("One (feat. Sanitarium)", DownloadFormat.tidyMetadata("One (feat. Sanitarium)"))
    }

    @Test
    fun `text that is not a trailing tag is never touched`() {
        assertEquals("Official Video Hits", DownloadFormat.tidyMetadata("Official Video Hits"))
        assertEquals("Live and Let Die", DownloadFormat.tidyMetadata("Live and Let Die"))
        assertEquals("Battery (Official Video) Live", DownloadFormat.tidyMetadata("Battery (Official Video) Live"))
        assertEquals("Battery Official Video", DownloadFormat.tidyMetadata("Battery Official Video"))
    }

    @Test
    fun `cleaning leaves unlisted tags alone and keeps values in step`() {
        val cleaned = input(
            title = "Battery (Official Video)",
            artists = listOf("Metallica - Topic"),
            albumTitle = "Master Of Puppets (Remastered)",
        ).cleaned()
        assertEquals("Battery", cleaned.title)
        assertEquals(listOf("Metallica"), cleaned.artists)
        assertEquals("Master Of Puppets (Remastered)", cleaned.albumTitle)
    }

    @Test
    fun `cleaned metadata is used by the folder template too`() {
        assertEquals(
            listOf("Metallica", "Master Of Puppets"),
            DownloadFormat.expand(input(artists = listOf("Metallica - Topic")).cleaned(), "%artist%/%album%"),
        )
    }

    @Test
    fun `the clean up switch off keeps metadata verbatim`() {
        val verbatim = input(title = "Battery (Official Video)", artists = listOf("Metallica - Topic"))
        assertEquals("Battery (Official Video)", verbatim.title)
        assertEquals(listOf("Metallica - Topic"), verbatim.artists)
        assertEquals(
            "Metallica - Topic - Master Of Puppets - Battery (Official Video).m4a",
            DownloadFormat.fileName(verbatim, DownloadFormat.DEFAULT_FILE_TEMPLATE, "audio/mp4"),
        )
        assertEquals(
            "Metallica - Master Of Puppets - Battery.m4a",
            DownloadFormat.fileName(verbatim.cleaned(), DownloadFormat.DEFAULT_FILE_TEMPLATE, "audio/mp4"),
        )
    }
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `/tmp/ktool/run-download-format-tests.sh`
Expected: FAIL - `error: unresolved reference: tidyMetadata` and `unresolved reference: cleaned`.

- [ ] **Step 3: Add the tidy pass**

```kotlin
    /**
     * Bracket tags the tidy pass removes. The list is closed on purpose: `(Remastered)`, `(Live)` and
     * `(feat. ...)` mark genuinely different releases, so removing them would collapse two tracks into one
     * file name.
     */
    private val TIDY_BRACKET_TAGS = setOf(
        "official video",
        "official music video",
        "official audio",
        "lyric video",
        "lyrics video",
        "visualiser",
        "visualizer",
        "audio",
        "hd",
        "4k",
        "mv",
    )

    /** A trailing `[...]` or `(...)` group, captured so its content can be judged before removal. */
    private val TRAILING_BRACKET = Regex("\\s*[\\[(]([^\\[\\]()]*)[\\])]\\s*$")
    private val TOPIC_SUFFIX = Regex("\\s+-\\s+topic\\s*$", RegexOption.IGNORE_CASE)
```

```kotlin
    /**
     * Removes video cruft from a metadata value: a trailing bracket group from [TIDY_BRACKET_TAGS], repeated
     * until stable, and a trailing `- Topic` artist suffix. Nothing inside the value is touched, so a title
     * that merely mentions a tag survives.
     */
    internal fun tidyMetadata(value: String): String {
        var current = value
        while (true) {
            val match = TRAILING_BRACKET.find(current) ?: break
            if (match.groupValues[1].trim().lowercase() !in TIDY_BRACKET_TAGS) break
            current = current.substring(0, match.range.first)
        }
        return current.replace(TOPIC_SUFFIX, "").trim()
    }
```

Add `cleaned()` to `Input` - the data class body is new, the fields are unchanged:

```kotlin
    data class Input(
        val songId: String,
        val title: String?,
        val artists: List<String>,
        val albumTitle: String?,
        val storedAlbumName: String?,
        val songYear: Int?,
        val albumYear: Int?,
        val bitrate: Int?,
        /** Album position from `song_album_map`, 1-based. Null when the song has no album row. */
        val trackNumber: Int? = null,
    ) {
        /**
         * The same metadata with the tidy pass applied, so `%artist%`, `%album%` and `%title%` agree whether
         * they are used in a folder template or a file-name template. Applied by the caller, which is what
         * makes the clean-up switch a switch.
         */
        fun cleaned(): Input = copy(
            title = title?.let(::tidyMetadata),
            artists = artists.map(::tidyMetadata),
            albumTitle = albumTitle?.let(::tidyMetadata),
            storedAlbumName = storedAlbumName?.let(::tidyMetadata),
        )
    }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `/tmp/ktool/run-download-format-tests.sh`
Expected: `OK (66 tests)` (eight new tests)

- [ ] **Step 5: Commit**

```bash
cd /data/clones/clone-vivizzz007-vivi-music
git add app/src/main/kotlin/com/music/vivi/playback/DownloadFormat.kt \
        app/src/test/kotlin/com/music/vivi/playback/DownloadFormatTest.kt
git commit -m "local: strip trailing video tags from download metadata"
```

---

## Task 6: Preferences for the file template and the clean-up switch

**Files:**
- Modify: `app/src/main/kotlin/com/music/vivi/playback/LocalDownloadPrefs.kt`

Unit-testing this step is not possible locally: `stringPreferencesKey` comes from `androidx.datastore`,
which needs the Android classpath. Verification is the code block below plus the CI build in Task 9.

- [ ] **Step 1: Add the two keys**

Append to `LocalDownloadPrefs.kt`:

```kotlin
/** File-name template such as `%artist% - %album% - %tracknumber% - %title%`; blank means the default. */
val DownloadFormatFileKey = stringPreferencesKey("downloadFormatFile")

/** Whether trailing video tags are stripped from metadata before it reaches a folder or file name. */
val DownloadFormatCleanKey = booleanPreferencesKey("downloadFormatClean")
```

- [ ] **Step 2: Verify the file is still balanced and consistent**

Run: `grep -n "PreferencesKey" app/src/main/kotlin/com/music/vivi/playback/LocalDownloadPrefs.kt`
Expected: five keys - `DownloadFolderExportEnabledKey`, `DownloadFolderUriKey`,
`DownloadFolderTemplateKey`, `DownloadFormatFileKey`, `DownloadFormatCleanKey`.

- [ ] **Step 3: Commit**

```bash
cd /data/clones/clone-vivizzz007-vivi-music
git add app/src/main/kotlin/com/music/vivi/playback/LocalDownloadPrefs.kt
git commit -m "local: add file format and clean-up preferences"
```

---

## Task 7: The album-position query

The only upstream contact this change adds. `song_album_map.index` is 0-based, populated by both album
insert paths in `DatabaseDao.kt` (`mapIndexed { index, song -> SongAlbumMap(..., index = index) }`), and
`DatabaseDao.kt` is the lowest-churn upstream file in the repository.

**Files:**
- Modify: `app/src/main/kotlin/com/music/vivi/db/DatabaseDao.kt` (after `getSongById`, around line 590)

- [ ] **Step 1: Add the query**

Insert directly after the existing `getSongById` declaration:

```kotlin
    /** The album position of [songId] in `song_album_map` (0-based), or null when it has no album row. */
    @Query("SELECT `index` FROM song_album_map WHERE songId = :songId LIMIT 1")
    suspend fun albumIndex(songId: String): Int?
```

The backticks around `index` are required: `INDEX` is a SQLite keyword.

- [ ] **Step 2: Verify the insertion is exactly three lines and nothing else moved**

Run: `git diff --stat app/src/main/kotlin/com/music/vivi/db/DatabaseDao.kt`
Expected: `1 file changed, 3 insertions(+)`

- [ ] **Step 3: Verify the column and table names against the entity**

Run: `grep -n "tableName\|index\|songId" app/src/main/kotlin/com/music/vivi/db/entities/SongAlbumMap.kt`
Expected: `tableName = "song_album_map"`, `songId: String`, `index: Int` - so the query above matches.

- [ ] **Step 4: Commit**

```bash
cd /data/clones/clone-vivizzz007-vivi-music
git add app/src/main/kotlin/com/music/vivi/db/DatabaseDao.kt
git commit -m "local: query the album position for track numbers"
```

Note for the reviewer: a wrong Room query fails the build, and there is no Android SDK here, so this
step is only fully verified by the CI run in Task 10.

---

## Task 8: Wire the exporter

**Files:**
- Modify: `app/src/main/kotlin/com/music/vivi/playback/DownloadFolderExporter.kt`

- [ ] **Step 1: Extend the `Song` mapping with the track number**

Replace the mapping at the bottom of the file:

```kotlin
/** Maps a library row onto the metadata the format can resolve. */
internal fun Song.toTemplateInput(trackNumber: Int? = null) = DownloadFormat.Input(
    songId = id,
    title = song.title,
    artists = artists.map { it.name },
    albumTitle = album?.title,
    storedAlbumName = song.albumName,
    songYear = song.year,
    albumYear = album?.year,
    bitrate = format?.bitrate,
    trackNumber = trackNumber,
)
```

- [ ] **Step 2: Read the new preferences, clean the metadata and use the file template**

Replace the body of the `try` block in `exportLocked` with:

```kotlin
        try {
            // Everything below is inside the try, including the metadata mapping and the preference reads:
            // export() is fired and forgotten from DownloadUtil's own scope, so nothing here may escape as
            // an uncaught exception.
            if (context.dataStore[DownloadFolderExportEnabledKey] == false) return
            val cleanUp = context.dataStore[DownloadFormatCleanKey] != false
            val input = song.toTemplateInput(albumPosition(songId))
                .let { if (cleanUp) it.cleaned() else it }
            val folderTemplate = DownloadFormat.templateOrDefault(context.dataStore[DownloadFolderTemplateKey])
            if (DownloadFormat.parse(folderTemplate).tooDeep) {
                Timber.tag(TAG).w(
                    "Template uses more than %d folders, the extra ones are ignored",
                    DownloadFormat.MAX_SEGMENTS,
                )
            }
            val fileTemplate = DownloadFormat.fileTemplateOrDefault(context.dataStore[DownloadFormatFileKey])
            val mimeType = sniffMimeType(songId)
                ?: song.format?.mimeType.orEmpty().substringBefore(';').trim()
                    .ifEmpty { DownloadFormat.DEFAULT_MIME_TYPE }
            val fileName = DownloadFormat.fileName(input, fileTemplate, mimeType)
            val segments = DownloadFormat.expand(input, folderTemplate)
            write(songId, fileName, mimeType, segments)
            Timber.tag(TAG).i("Exported %s as %s", songId, fileName)
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            Timber.tag(TAG).e(e, "Export failed for %s, cached download is intact", songId)
        }
```

- [ ] **Step 3: Add the album-position lookup**

Add below `exportLocked`:

```kotlin
    /**
     * The album position converted to a 1-based track number, or null when the song has no album row (a
     * download taken straight from search or a playlist). A failing lookup is logged and treated as absent:
     * the export still runs, it just carries no track number.
     */
    private suspend fun albumPosition(songId: String): Int? = try {
        database.albumIndex(songId)?.plus(1)
    } catch (e: CancellationException) {
        throw e
    } catch (e: Exception) {
        Timber.tag(TAG).w(e, "Could not read the album position of %s", songId)
        null
    }
```

- [ ] **Step 4: Verify no reference to the renamed API is left and the contracts are intact**

Run: `grep -n "DownloadFormat\.\|albumPosition\|toTemplateInput" app/src/main/kotlin/com/music/vivi/playback/DownloadFolderExporter.kt`
Expected: `toTemplateInput(albumPosition(songId))`, `DownloadFormat.templateOrDefault`,
`DownloadFormat.parse`, `DownloadFormat.MAX_SEGMENTS`, `DownloadFormat.fileTemplateOrDefault`,
`DownloadFormat.fileName`, `DownloadFormat.expand`, `DownloadFormat.DEFAULT_MIME_TYPE` - and the write
path, destinations, staging and rename code untouched.

- [ ] **Step 5: Commit**

```bash
cd /data/clones/clone-vivizzz007-vivi-music
git add app/src/main/kotlin/com/music/vivi/playback/DownloadFolderExporter.kt
git commit -m "local: export with the file format template and track numbers"
```

---

## Task 9: Settings - the Download format group and the file dialog

**Files:**
- Modify: `app/src/main/res/values/local_download_strings.xml`
- Modify: `app/src/main/kotlin/com/music/vivi/ui/screens/settings/LocalDownloadSettings.kt`

There are no Compose unit tests here (no Robolectric in this environment), so verification is a clean
`grep` audit of every referenced string and symbol plus the CI build in Task 10.

- [ ] **Step 1: Update the strings**

Replace `local_download_strings.xml` with:

```xml
<?xml version="1.0" encoding="utf-8"?>
<!--
  Strings for the "save downloads to a folder" patch.
  Kept in their own file so that the patch never has to touch vivi_strings.xml, which upstream edits
  on nearly every release.
-->
<resources>
    <string name="download_folder">Download folder</string>
    <string name="download_folder_export">Save downloads to a folder</string>
    <string name="download_folder_default">Music/Vivi (default)</string>
    <string name="download_folder_current">Folder: %1$s</string>
    <string name="download_folder_pick">Choose folder</string>
    <string name="download_folder_reset">Use the default folder</string>
    <string name="download_folder_checking">Checking folder access...</string>
    <string name="download_folder_off">Disabled, downloads stay hidden in the app cache</string>
    <string name="download_folder_permission_lost">Folder access lost, using Music/Vivi. Choose the folder again.</string>
    <string name="download_folder_structure_flat">Flat - save directly in the chosen folder</string>
    <string name="download_folder_structure_hint">Use the tokens below, separated by /. Leave empty to save directly in the chosen folder.</string>
    <string name="download_folder_structure_preview">Preview</string>
    <string name="download_folder_structure_unknown_token">Unknown token: %1$s</string>
    <string name="download_folder_structure_too_deep">Only the first 6 folders are used</string>
    <string name="download_folder_default_root">Music/Vivi</string>
    <string name="download_format">Download format</string>
    <string name="download_format_folder">Folder format</string>
    <string name="download_format_file">File format</string>
    <string name="download_format_file_hint">Use the tokens below. A token with no value disappears together with its separator; the track name is always kept.</string>
    <string name="download_format_clean">Clean up names</string>
    <string name="download_format_clean_desc">Removes trailing video tags such as (Official Video), [HD] and - Topic</string>
</resources>
```

Note what changed: `download_folder_structure` is gone (it becomes the "Folder format" row label) and
six `download_format*` strings are new. The other folder strings are reused by both dialogs.

- [ ] **Step 2: Rewrite the settings file**

Replace `app/src/main/kotlin/com/music/vivi/ui/screens/settings/LocalDownloadSettings.kt` with:

```kotlin
/**
 * vivimusic Project (C) 2026
 * Licensed under GPL-3.0 | See git history for contributors
 */

package com.music.vivi.ui.screens.settings

import android.content.Context
import android.content.Intent
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.AssistChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.TextRange
import androidx.compose.ui.text.input.TextFieldValue
import androidx.compose.ui.unit.dp
import androidx.core.net.toUri
import com.music.vivi.LocalDatabase
import com.music.vivi.R
import com.music.vivi.db.entities.Song
import com.music.vivi.playback.DownloadFolderExportEnabledKey
import com.music.vivi.playback.DownloadFolderTemplateKey
import com.music.vivi.playback.DownloadFolderUriKey
import com.music.vivi.playback.DownloadFormat
import com.music.vivi.playback.DownloadFormatCleanKey
import com.music.vivi.playback.DownloadFormatFileKey
import com.music.vivi.playback.SafFolders
import com.music.vivi.playback.toTemplateInput
import com.music.vivi.ui.component.ActionPromptDialog
import com.music.vivi.ui.component.ExpressiveSettingGroup
import com.music.vivi.ui.component.Material3SettingsItem
import com.music.vivi.utils.rememberPreference
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.isActive
import kotlinx.coroutines.withContext
import timber.log.Timber

/** Which template a [DownloadFormatDialog] is editing. */
private enum class FormatField { Folder, File }

/**
 * Storage settings group for the "save downloads to a folder" patch.
 *
 * It lives in its own file so that the only change upstream sees is a single call to
 * [LocalDownloadSettingsGroup] in `StorageSettings.kt`.
 */
@Composable
fun LocalDownloadSettingsGroup() {
    val context = LocalContext.current
    val (exportEnabled, onExportEnabledChange) =
        rememberPreference(DownloadFolderExportEnabledKey, true)
    val (folderUri, onFolderUriChange) = rememberPreference(DownloadFolderUriKey, "")
    val (folderTemplate, onFolderTemplateChange) =
        rememberPreference(DownloadFolderTemplateKey, DownloadFormat.DEFAULT_FOLDER_TEMPLATE)
    val (fileTemplate, onFileTemplateChange) = rememberPreference(DownloadFormatFileKey, "")
    val (cleanUp, onCleanUpChange) = rememberPreference(DownloadFormatCleanKey, true)
    val database = LocalDatabase.current
    var editing by remember { mutableStateOf<FormatField?>(null) }
    var sampleSong by remember { mutableStateOf<Song?>(null) }
    var sampleTrackNumber by remember { mutableStateOf<Int?>(null) }

    // A real downloaded song makes the preview honest; the library may be empty.
    LaunchedEffect(Unit) {
        val (song, trackNumber) = withContext(Dispatchers.IO) {
            val found = database.downloadedSongsByCreateDateAsc().first().lastOrNull()
            found to found?.let { database.albumIndex(it.id)?.plus(1) }
        }
        sampleSong = song
        sampleTrackNumber = trackNumber
    }

    var folderName by remember(folderUri) { mutableStateOf<String?>(null) }
    // Starts true when a folder is configured, so the description does not flash "access lost" before the
    // provider answers.
    var resolving by remember(folderUri) { mutableStateOf(folderUri.isNotBlank()) }

    // Resolving the display name touches the documents provider, so keep it off the main thread. A
    // null result is how a revoked grant shows up: the provider throws, and SafFolders reports null.
    LaunchedEffect(folderUri) {
        folderName = null
        resolving = folderUri.isNotBlank()
        if (folderUri.isNotBlank()) {
            val resolved = withContext(Dispatchers.IO) {
                SafFolders.displayName(context, folderUri.toUri())
            }
            // A newer folder may already have been picked while this lookup was running.
            if (isActive) {
                folderName = resolved
                resolving = false
            }
        }
    }

    val pickFolder =
        rememberLauncherForActivityResult(ActivityResultContracts.OpenDocumentTree()) { uri ->
            if (uri != null) {
                runCatching {
                    context.contentResolver.takePersistableUriPermission(
                        uri,
                        Intent.FLAG_GRANT_READ_URI_PERMISSION or
                            Intent.FLAG_GRANT_WRITE_URI_PERMISSION,
                    )
                }.onFailure { Timber.tag(TAG).w(it, "Could not persist folder permission") }

                // Switching folders must not leak the previous grant, whether or not the new one could be
                // persisted; re-picking the same folder must not release the grant we just took either.
                if (uri.toString() != folderUri) releasePersistedPermission(context, folderUri)
                // Stored either way: the grant may still be alive for this session, and the exporter falls
                // back to Music/Vivi (and the description says so) when it is not.
                onFolderUriChange(uri.toString())
            }
        }

    ExpressiveSettingGroup(
        title = stringResource(R.string.download_folder),
        items = buildList {
            add(
                Material3SettingsItem(
                    icon = painterResource(R.drawable.download),
                    title = { Text(stringResource(R.string.download_folder_export)) },
                    description = {
                        val name = folderName
                        Text(
                            text = when {
                                !exportEnabled -> stringResource(R.string.download_folder_off)
                                folderUri.isBlank() ->
                                    stringResource(R.string.download_folder_default)
                                resolving -> stringResource(R.string.download_folder_checking)
                                name != null -> stringResource(R.string.download_folder_current, name)
                                else -> stringResource(R.string.download_folder_permission_lost)
                            },
                        )
                    },
                    trailingContent = {
                        Switch(
                            checked = exportEnabled,
                            onCheckedChange = onExportEnabledChange,
                        )
                    },
                    onClick = { onExportEnabledChange(!exportEnabled) },
                ),
            )
            if (exportEnabled) {
                add(
                    Material3SettingsItem(
                        icon = painterResource(R.drawable.storage),
                        title = { Text(stringResource(R.string.download_folder_pick)) },
                        onClick = { pickFolder.launch(null) },
                    ),
                )
            }
            if (folderUri.isNotBlank()) {
                add(
                    Material3SettingsItem(
                        icon = painterResource(R.drawable.clear_all),
                        title = { Text(stringResource(R.string.download_folder_reset)) },
                        onClick = {
                            releasePersistedPermission(context, folderUri)
                            onFolderUriChange("")
                        },
                    ),
                )
            }
        },
    )

    // The naming rows move into their own group so one place answers "what will my downloads look like on
    // disk": the folder row is moved here, never duplicated.
    if (exportEnabled) {
        ExpressiveSettingGroup(
            title = stringResource(R.string.download_format),
            items = listOf(
                Material3SettingsItem(
                    icon = painterResource(R.drawable.list),
                    title = { Text(stringResource(R.string.download_format_folder)) },
                    description = {
                        Text(
                            text = folderTemplate.ifBlank {
                                stringResource(R.string.download_folder_structure_flat)
                            },
                        )
                    },
                    onClick = { editing = FormatField.Folder },
                ),
                Material3SettingsItem(
                    icon = painterResource(R.drawable.edit),
                    title = { Text(stringResource(R.string.download_format_file)) },
                    description = { Text(DownloadFormat.fileTemplateOrDefault(fileTemplate)) },
                    onClick = { editing = FormatField.File },
                ),
            ),
        )
    }

    val field = editing
    if (field != null) {
        DownloadFormatDialog(
            field = field,
            folderTemplate = folderTemplate,
            fileTemplate = DownloadFormat.fileTemplateOrDefault(fileTemplate),
            rootLabel = folderName ?: stringResource(R.string.download_folder_default_root),
            sampleSong = sampleSong,
            sampleTrackNumber = sampleTrackNumber,
            cleanUp = cleanUp,
            onCleanUpChange = onCleanUpChange,
            onDismiss = { editing = null },
            onSave = { saved ->
                if (field == FormatField.Folder) {
                    onFolderTemplateChange(saved)
                } else {
                    onFileTemplateChange(saved)
                }
                editing = null
            },
        )
    }
}

private fun releasePersistedPermission(context: Context, folderUri: String) {
    if (folderUri.isBlank()) return
    runCatching {
        context.contentResolver.releasePersistableUriPermission(
            folderUri.toUri(),
            Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_WRITE_URI_PERMISSION,
        )
    }
}

/**
 * One dialog for both templates: the field being edited is the draft, and the preview always shows the
 * full resulting path, so the two templates are visibly composed together.
 */
@Composable
private fun DownloadFormatDialog(
    field: FormatField,
    folderTemplate: String,
    fileTemplate: String,
    rootLabel: String,
    sampleSong: Song?,
    sampleTrackNumber: Int?,
    cleanUp: Boolean,
    onCleanUpChange: (Boolean) -> Unit,
    onDismiss: () -> Unit,
    onSave: (String) -> Unit,
) {
    val editingFile = field == FormatField.File
    val initial = if (editingFile) fileTemplate else folderTemplate
    val default = if (editingFile) DownloadFormat.DEFAULT_FILE_TEMPLATE else DownloadFormat.DEFAULT_FOLDER_TEMPLATE
    var draft by remember(initial) { mutableStateOf(TextFieldValue(initial)) }
    val result = DownloadFormat.parse(draft.text)

    // The example keeps the preview meaningful on a fresh install with nothing downloaded yet.
    val example = DownloadFormat.Input(
        songId = "dQw4w9WgXcQ",
        title = "Enter Sandman",
        artists = listOf("Metallica"),
        albumTitle = "Master Of Puppets",
        storedAlbumName = null,
        songYear = 1986,
        albumYear = null,
        bitrate = 256_000,
        trackNumber = 10,
    )
    val rawInput = sampleSong?.toTemplateInput(sampleTrackNumber) ?: example
    val previewInput = if (cleanUp) rawInput.cleaned() else rawInput
    // The draft is previewed, so the effect of an edit is visible before saving.
    val previewFolders = DownloadFormat.expand(
        previewInput,
        if (editingFile) folderTemplate else draft.text,
    )
    // No extension in the preview: the real one is decided at export time from the cached bytes.
    val previewName = DownloadFormat.fileNameBase(
        previewInput,
        if (editingFile) draft.text else fileTemplate,
    )
    val preview = (listOf(rootLabel) + previewFolders + previewName).joinToString("/")

    ActionPromptDialog(
        title = stringResource(
            if (editingFile) R.string.download_format_file else R.string.download_format_folder,
        ),
        onDismiss = onDismiss,
        onConfirm = { if (result.isValid) onSave(draft.text) },
        onReset = { draft = TextFieldValue(default) },
        onCancel = onDismiss,
    ) {
        OutlinedTextField(
            value = draft,
            onValueChange = { draft = it },
            modifier = Modifier.fillMaxWidth(),
            singleLine = true,
            isError = !result.isValid,
            label = {
                Text(
                    stringResource(
                        if (editingFile) R.string.download_format_file else R.string.download_format_folder,
                    ),
                )
            },
        )
        if (result.unknownTokens.isNotEmpty()) {
            Text(
                text = stringResource(
                    R.string.download_folder_structure_unknown_token,
                    result.unknownTokens.joinToString(", "),
                ),
                color = MaterialTheme.colorScheme.error,
                style = MaterialTheme.typography.bodySmall,
            )
        } else if (result.tooDeep && !editingFile) {
            Text(
                text = stringResource(R.string.download_folder_structure_too_deep),
                style = MaterialTheme.typography.bodySmall,
            )
        }
        FlowRow(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            DownloadFormat.TOKENS.forEach { token ->
                AssistChip(
                    onClick = { draft = draft.insertAtCursor(token) },
                    label = { Text(token) },
                )
            }
        }
        Column(modifier = Modifier.fillMaxWidth()) {
            Text(
                text = stringResource(R.string.download_folder_structure_preview),
                style = MaterialTheme.typography.labelLarge,
            )
            Text(text = preview, style = MaterialTheme.typography.bodySmall)
            Text(
                text = stringResource(
                    if (editingFile) {
                        R.string.download_format_file_hint
                    } else {
                        R.string.download_folder_structure_hint
                    },
                ),
                modifier = Modifier.padding(top = 8.dp),
                style = MaterialTheme.typography.bodySmall,
            )
            // Cleaning changes folder names as well as file names, so the switch is explained where the
            // naming rules live.
            if (editingFile) {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(top = 12.dp),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text(
                        text = stringResource(R.string.download_format_clean),
                        style = MaterialTheme.typography.bodyMedium,
                    )
                    Switch(checked = cleanUp, onCheckedChange = onCleanUpChange)
                }
                Text(
                    text = stringResource(R.string.download_format_clean_desc),
                    style = MaterialTheme.typography.bodySmall,
                )
            }
        }
    }
}

private fun TextFieldValue.insertAtCursor(text: String): TextFieldValue {
    // A backwards selection reports start after end, which replaceRange would reject.
    val start = minOf(selection.start, selection.end).coerceAtLeast(0)
    val end = maxOf(selection.start, selection.end).coerceAtLeast(0)
    return copy(
        text = this.text.replaceRange(start, end, text),
        selection = TextRange(start + text.length),
    )
}

private const val TAG = "LocalDownloadSettings"
```

- [ ] **Step 3: Audit every referenced string and symbol**

Run:

```bash
cd /data/clones/clone-vivizzz007-vivi-music
grep -o "R\.string\.[a-z_0-9]*" app/src/main/kotlin/com/music/vivi/ui/screens/settings/LocalDownloadSettings.kt \
  | sort -u | sed 's/R\.string\.//' > /tmp/used-strings.txt
grep -o 'name="[a-z_0-9]*"' app/src/main/res/values/local_download_strings.xml \
  | sed 's/name="//; s/"//' | sort -u > /tmp/defined-strings.txt
comm -23 /tmp/used-strings.txt /tmp/defined-strings.txt
```

Expected: no output (every string used is defined). Then confirm nothing else referenced the removed
`download_folder_structure` string:

```bash
grep -rn "download_folder_structure\"" app/src/main/ || echo "none"
```

Expected: `none`

- [ ] **Step 4: Confirm the XML is well formed**

Run:

```bash
python3 -c "import xml.etree.ElementTree as ET; ET.parse('app/src/main/res/values/local_download_strings.xml'); print('XML OK')"
```

Expected: `XML OK`

- [ ] **Step 5: Commit**

```bash
cd /data/clones/clone-vivizzz007-vivi-music
git add app/src/main/res/values/local_download_strings.xml \
        app/src/main/kotlin/com/music/vivi/ui/screens/settings/LocalDownloadSettings.kt
git commit -m "local: move folder format into a download format group and add file format"
```

---

## Task 10: Delivery - harness, patch, fork CI, documentation

**Files:**
- Modify: `/tmp/vivi-fork/local-patches/01-download-folder.patch` (regenerated deliverable)
- Modify: `/tmp/vivi-fork/local-patches/README.md`

- [ ] **Step 1: Run the full local suite one last time and record the count**

Run: `/tmp/ktool/run-download-format-tests.sh`
Expected: `OK (66 tests)` (or the final count after any review fixes) - all green, no failures.

- [ ] **Step 2: Confirm the whole branch is committed**

Run: `git status --short`
Expected: no output

- [ ] **Step 3: Regenerate the patch from upstream main, app tree only**

```bash
cd /data/clones/clone-vivizzz007-vivi-music
git diff main -- app/ > /tmp/01-download-folder.patch
wc -l /tmp/01-download-folder.patch
```

- [ ] **Step 4: Prove the patch still applies to pristine upstream main**

```bash
cd /data/clones/clone-vivizzz007-vivi-music
git worktree add --detach /tmp/vivi-patch-check main
cd /tmp/vivi-patch-check && git apply --check /tmp/01-download-folder.patch && echo "APPLIES"
```

Expected: `APPLIES` with no reject output. Remove the worktree afterwards:
`git worktree remove /tmp/vivi-patch-check --force` from the main clone.

- [ ] **Step 5: Confirm the patch carries no documentation file**

Run: `grep -c "^diff --git a/docs" /tmp/01-download-folder.patch || echo "0"`
Expected: `0`

- [ ] **Step 6: Update the fork README**

In `/tmp/vivi-fork/local-patches/README.md`:

1. In **What patch 01 does**, extend the template bullet to:

```markdown
- Optional folder structure template applied under whichever root is active, edited in
  *Settings -> Storage -> Download format -> Folder format*. It defaults to `%artist%/%album%`;
  `%artist%`, `%album%`, `%year%`, `%title%`, `%songId%`, `%quality%` and `%tracknumber%` are supported,
  an unresolvable token becomes `Unknown Artist` / `Unknown Album` / `Unknown Year` / `Unknown Quality`,
  and an explicitly emptied template means flat output directly in the root.
- Optional **file-name** template in *Settings -> Storage -> Download format -> File format*, defaulting to
  `%artist% - %album% - %tracknumber% - %title%`, so an album download lands as
  `Metallica - Master Of Puppets - 10 - Battery.webm` and sorts in album order. A part whose token has no
  value disappears together with its separator, and an emptied or blank file template means the built-in
  default. Track numbers come from the album position already stored in `song_album_map` (two digits up to
  99, raw above), so a download taken from a search or playlist, which has no album row, simply carries no
  number.
- Optional **clean up names** switch (on by default) inside the File format dialog: a trailing bracket tag
  from a fixed list (`(Official Video)`, `[HD]`, `(Official Audio)`, `[4K]`, ...) and a trailing `- Topic`
  artist suffix are removed before either template is expanded. `(Remastered)`, `(Live)` and `(feat. ...)`
  are deliberately kept.
```

2. Change the footprint sentence to:

```markdown
Footprint: 8 new files, plus **33 added lines** in four upstream files -
`DownloadUtil.kt` (constructor parameter + one call in the `STATE_COMPLETED` branch),
`StorageSettings.kt` (one call to `LocalDownloadSettingsGroup()`),
`app/build.gradle.kts` (Kover wiring and `testImplementation(libs.junit)` for the new unit tests) and
`DatabaseDao.kt` (a three-line suspend query for the album position).
```

3. Add rows to **Known limitations**:

```markdown
| No disc numbers | Nothing in the schema records a disc number, so `%disc%` does not exist; a multi-disc album numbers tracks continuously within one `song_album_map` row set. |
| An exotic separator can leave punctuation behind | The tidy pass collapses and trims `-`, `–`, `.`, `,`, `_` and whitespace. A template that separates parts with something else (for example `%tracknumber% ~ %title%`) can leave the `~` behind when the token is empty. The dialog preview shows the real result before saving. |
| A name longer than 240 bytes is elided in the middle | `Metallica - Master Of Puppets - 05 - The Thin...Not Be (Remastered).webm` keeps the start and the tail of the track name, joined by `...`, so the track name is never lost to a tail truncation. |
| Clean-up is metadata-only and not retroactive | Turning the switch on does not rename files that already exist, and it never edits text in the middle of a title. |
```

4. In **Coverage gate and named debt**, replace the `FolderTemplate*` include with
`com.music.vivi.playback.DownloadFormat*`.

5. In **Notes**, extend the on-device checklist with:

```markdown
- On-device checklist for the file-name format: download a whole album and confirm the file manager lists
  it in album order with two-digit numbers (`... - 01 - ...`); download a song from search (no album row)
  and confirm the name has no number and no doubled `-`; turn the clean-up switch off and re-download a
  video-sourced track to confirm the `(Official Video)` tag comes back; with the switch on, confirm it is
  gone and that `(Remastered)` survives; set a long, silly template and confirm the name keeps its end and
  the extension; clear the file template and confirm the default returns.
```

- [ ] **Step 7: Publish the patch and the README to the fork**

```bash
cp /tmp/01-download-folder.patch /tmp/vivi-fork/local-patches/01-download-folder.patch
cd /tmp/vivi-fork
git add -A
git status --short
git commit -m "local: file-name template with track numbers (patch 01 update)"
git -c credential.helper='!gh auth git-credential' push fork fork-main:main
```

- [ ] **Step 8: Wait for CI and read the result**

```bash
gh run list --repo binhex/vivi-music --workflow local-build.yml --limit 3
gh run watch <run-id> --repo binhex/vivi-music
```

Expected: the `foss debug APK` job succeeds, including `testUniversalFossDebugUnitTest` and the
`koverVerify` 95% line gate. On failure: `gh run view <run-id> --log-failed`, fix on
`local/download-folder`, then repeat Steps 3-8.

- [ ] **Step 9: Confirm the artefact and record the checksum**

```bash
gh run view <run-id> --repo binhex/vivi-music
```

Expected: an artefact named `vivi-foss-debug-<upstream-sha>` and a `sha256sum` line in the run summary.

- [ ] **Step 10: Confirm the working tree is clean and the branch is the deliverable**

Run: `git status --short && git log --oneline -8`
Expected: no output from `git status`; the eight commits from Tasks 0-9 visible on
`local/download-folder`.

---

## Self-review notes

**Spec coverage.** Every spec section maps to a task: unit rename and grammar to Tasks 1-2; the file-name
template, absence handling and the tidy pass to Tasks 3-5; the 240-byte budgets and middle elision to
Task 4; clean-up rules and the switch to Task 5 (rules) and Tasks 6, 9 (switch); the track-number source
to Task 7 (query) and Tasks 2, 8 (resolution and fetch); the settings group and dialog to Task 9;
strings to Task 9; the Kover include rename to Task 1; delivery and documentation to Task 10; the spec's
testing list to Tasks 2-5. Upstream contact is the DAO query only, asserted in Task 7 Step 2 and audited
in Task 10 Step 5.

**Placeholders.** None. Every code step carries the full code, every command has an expected result, and
every test step names the failure or the count to expect.

**Type consistency.** `DownloadFormat.fileName(input, template, mimeType)` and
`fileNameBase(input, template)` are used with exactly those shapes in Tasks 3, 4, 8 and 9;
`DownloadFormat.Input` gains only `trackNumber` (Task 2) and only `cleaned()` (Task 5), and the test
helper is extended with the same field in the same task; `trackNumberText(Int?)`, `tidyMetadata(String)`,
`elideMiddle(String, Int)` and `truncateTailToBytes(String, Int)` are defined in the task that first
calls them; `DEFAULT_FOLDER_TEMPLATE` / `DEFAULT_FILE_TEMPLATE` replace `DEFAULT_TEMPLATE` in Task 3 and
every later reference uses the new names; `database.albumIndex(String): Int?` is defined in Task 7 and
consumed in Tasks 8 and 9.

**Deliberate deviations from the spec, and why.**

1. *File-name signature.* The spec writes `DownloadFormat.fileName(input, mimeType)`. The template is
   passed explicitly instead (`fileName(input, template, mimeType)`) so the dialog preview and the
   exporter share one rule and the unit stays free of preference lookups.
2. *Folder fallbacks versus file-name absence.* The spec's example `Metallica - Battery.webm` ("artist is
   the only survivor") requires an absent album to vanish rather than become `Unknown Album`, while the
   45 existing tests require `expand` to keep the `Unknown *` fallbacks so a folder tree stays
   predictable. Both are honoured with one flag: the folder path keeps its fallbacks, the file-name path
   drops absent parts. The title is the exception in both paths - it never disappears, falling back to the
   song id.
3. *Tidy separator set.* The spec calls `%tracknumber%. %title%` an unsupported case; `.` is in the tidy
   set here, so that example works and the documented limitation is narrower (it applies to separators
   outside `-`, `–`, `.`, `,`, `_`, whitespace).
4. *Elision ratio.* The spec's elided example is illustrative; the implementation splits the budget evenly
   between head and tail around a three-byte `...`, which is what Task 4's exact-string test pins down.
5. *Signatures of the renamed unit.* `object FolderTemplate` → `object DownloadFormat`,
   `DEFAULT_TEMPLATE` → `DEFAULT_FOLDER_TEMPLATE`, `Song.toTemplateInput(trackNumber: Int? = null)`.

**Known risk.** No Android SDK or JDK 21 here, so Room (`albumIndex`), DataStore keys, the Compose dialog
and the XML strings are verified only by inspection plus the fork CI run in Task 10. That is the same
arrangement the previous plan used, and it is why Task 10 is not optional.
