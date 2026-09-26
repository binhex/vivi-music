# Templated Download Folder Structure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use sub-agents (recommended) to implement this plan
> task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the user describe the download subfolder structure with tokens such as
`%artist%/%album%`, applied under whichever download root is active, defaulting to
`%artist%/%album%`.

**Architecture:** One new pure-Kotlin unit (`FolderTemplate`) owns every path rule: token parsing,
token resolution, segment sanitising and file-name composition. The existing
`DownloadFolderExporter` stops composing names itself and instead asks `FolderTemplate` for segments
and a file name, then hands those to each destination writer (MediaStore `RELATIVE_PATH`, the SAF
tree walk in `SafFolders`, or the API 26-28 app directory). The settings editor is a dialog in
`LocalDownloadSettings.kt` that validates through the same `parse` used by the exporter's rules.

**Tech Stack:** Kotlin 2.3.10, Jetpack Compose (Material3), Hilt, Media3 1.7.1, Room, Storage Access
Framework, JUnit 4.13.2, GitHub Actions (fork CI).

**Spec:** `docs/agent/specs/2026-09-23-download-folder-structure-design.md` (approved). Read it before starting.

---

## Working environment (read first)

- **Repo:** `/data/clones/clone-vivizzz007-vivi-music`, branch `local/download-folder`. This branch
  holds the whole patch series plus the spec; `main` is pristine upstream. Never commit on `main`.
- **No Android SDK and no JDK 21 in this environment.** `./gradlew` cannot run here. Local
  verification is the pure-Kotlin harness below; the authoritative verification for anything Android
  is the fork's CI.
- **Fork:** `binhex/vivi-music` (public fork of upstream, additive only). The patch set and workflows
  live there, staged in a worktree at `/tmp/vivi-fork` (branch `fork-main`). Push from that worktree
  with:

  ```bash
  cd /tmp/vivi-fork && git -c credential.helper='!gh auth git-credential' push fork fork-main:main
  ```

- **CI:** `gh run list --repo binhex/vivi-music --workflow local-build.yml --limit 3` and `gh run view
  <id> --repo binhex/vivi-music`. Failures: `gh run view <id> --log-failed`. The APK artifact is named
  `vivi-foss-debug-<upstream-sha>`.
- **Patch generation (delivery only, Task 8):** `git diff main..local/download-folder -- app/ >
  local-patches/01-download-folder.patch`. The `-- app/` pathspec is deliberate: specs and plans must
  never be pushed into upstream's source tree by the patch.
- **Upstream contact budget:** the patch may add only the existing four lines in `DownloadUtil.kt` and
  `StorageSettings.kt`, plus the single `testImplementation(libs.junit)` line. Every other change must
  be a new file or a line inside our own files.
- **Never commit:** temp files, `/tmp` scripts, or anything under `docs/agent/` into the patch.

### Local test harness for the pure unit

Already installed in this environment at `/tmp/ktool`. If missing, recreate it:

```bash
mkdir -p /tmp/ktool && cd /tmp/ktool
curl -sSL -o kotlin2310.zip https://github.com/JetBrains/kotlin/releases/download/v2.3.10/kotlin-compiler-2.3.10.zip
unzip -q -o kotlin2310.zip -d .
curl -sSL -o junit.jar https://repo1.maven.org/maven2/junit/junit/4.13.2/junit-4.13.2.jar
curl -sSL -o hamcrest.jar https://repo1.maven.org/maven2/org/hamcrest/hamcrest-core/1.3/hamcrest-core-1.3.jar
```

Create `/tmp/ktool/run-folder-template-tests.sh` (temp file, never committed):

```bash
#!/usr/bin/env bash
# Compiles FolderTemplate + its test with a standalone Kotlin compiler and runs JUnit directly.
set -euo pipefail

REPO=/data/clones/clone-vivizzz007-vivi-music
TOOL=/tmp/ktool
SRC="$REPO/app/src/main/kotlin/com/music/vivi/playback/FolderTemplate.kt"
TEST="$REPO/app/src/test/kotlin/com/music/vivi/playback/FolderTemplateTest.kt"

rm -rf "$TOOL/out" && mkdir -p "$TOOL/out"

"$TOOL/kotlinc2310/kotlinc/bin/kotlinc" -nowarn \
  -cp "$TOOL/junit.jar:$TOOL/hamcrest.jar" \
  -d "$TOOL/out" "$SRC" "$TEST"

java -cp "$TOOL/out:$TOOL/junit.jar:$TOOL/hamcrest.jar:$TOOL/kotlinc2310/kotlinc/lib/kotlin-stdlib.jar" \
  org.junit.runner.JUnitCore com.music.vivi.playback.FolderTemplateTest
```

Run it as `/tmp/ktool/run-folder-template-tests.sh`. Expected output on success:

```text
JUnit version 4.13.2
............
Time: 0.0xx

OK (N tests)
```

On a compile error, kotlinc exits non-zero and prints `error: unresolved reference: ...` — that is
the RED signal for a new symbol.

### File map

| Path | Action | Responsibility |
| --- | --- | --- |
| `app/src/main/kotlin/com/music/vivi/playback/FolderTemplate.kt` | create | Pure path rules: `parse`, `expand`, `fileName`, sanitising, truncation. No Android or DB imports. |
| `app/src/main/kotlin/com/music/vivi/playback/LocalDownloadPrefs.kt` | modify | Add `DownloadFolderTemplateKey`. |
| `app/src/main/kotlin/com/music/vivi/playback/SafFolders.kt` | modify | Add `resolveDirectory`; generalise `findFile`/`createFile` to any parent document. |
| `app/src/main/kotlin/com/music/vivi/playback/DownloadFolderExporter.kt` | modify | Read the template, map `Song` to `FolderTemplate.Input`, pass segments to the three writers, stop composing names locally. |
| `app/src/main/kotlin/com/music/vivi/ui/screens/settings/LocalDownloadSettings.kt` | modify | Structure row plus editor dialog (field, token chips, preview, validation). |
| `app/src/main/res/values/local_download_strings.xml` | modify | Seven new strings. |
| `app/src/test/kotlin/com/music/vivi/playback/FolderTemplateTest.kt` | create | Unit tests for the pure unit. |
| `app/build.gradle.kts` | modify | `testImplementation(libs.junit)`. |
| `.github/workflows/local-build.yml` *(fork, not in the patch)* | modify | Run the unit tests in CI. |
| `local-patches/README.md` *(fork, not in the patch)* | modify | Document the feature and its limitations. |
| `local-patches/01-download-folder.patch` *(fork, not in the patch)* | regenerate | The deliverable. |

---

## Task 1: `FolderTemplate.parse` and the test source set

**Files:**

- Create: `app/src/test/kotlin/com/music/vivi/playback/FolderTemplateTest.kt`
- Create: `app/src/main/kotlin/com/music/vivi/playback/FolderTemplate.kt`
- Modify: `app/build.gradle.kts:226`

- [ ] **Step 1: Write the failing tests for `parse`**

Create `app/src/test/kotlin/com/music/vivi/playback/FolderTemplateTest.kt`:

```kotlin
/**
 * vivimusic Project (C) 2026
 * Licensed under GPL-3.0 | See git history for contributors
 */

package com.music.vivi.playback

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class FolderTemplateTest {

    private fun input(
        songId: String = "dQw4w9WgXcQ",
        title: String? = "Enter Sandman",
        artists: List<String> = listOf("Metallica"),
        album: String? = "Master Of Puppets",
        year: Int? = 1986,
        bitrate: Int? = 256_000,
    ) = FolderTemplate.Input(songId, title, artists, album, year, bitrate)

    @Test
    fun `parse reports unknown tokens`() {
        val result = FolderTemplate.parse("%artist%/%genre%/%bogus%")
        assertEquals(listOf("genre", "bogus"), result.unknownTokens)
        assertFalse(result.isValid)
    }

    @Test
    fun `parse accepts the default template`() {
        assertTrue(FolderTemplate.parse(FolderTemplate.DEFAULT_TEMPLATE).isValid)
    }

    @Test
    fun `parse is case insensitive`() {
        assertTrue(FolderTemplate.parse("%ARTIST%/%Album%").isValid)
    }

    @Test
    fun `parse flags a too deep template without invalidating it`() {
        val result = FolderTemplate.parse((1..7).joinToString("/") { "%artist%" })
        assertTrue(result.tooDeep)
        assertTrue(result.isValid)
    }
}
```

- [ ] **Step 2: Add the test dependency**

Modify `app/build.gradle.kts` — the dependencies block starts at line 223:

```kotlin
dependencies {
    implementation(libs.guava)
    implementation(libs.coroutines.guava)
    implementation(libs.concurrent.futures)
    testImplementation(libs.junit)
```

(`libs.junit` already exists in `gradle/libs.versions.toml` as `junit = "4.13.2"`; only this one line is new.)

- [ ] **Step 3: Run the tests to verify they fail**

```bash
/tmp/ktool/run-folder-template-tests.sh
```

Expected: FAIL — `error: unresolved reference: FolderTemplate` (the unit does not exist yet).

- [ ] **Step 4: Write the minimal `FolderTemplate` skeleton**

Create `app/src/main/kotlin/com/music/vivi/playback/FolderTemplate.kt`:

```kotlin
/**
 * vivimusic Project (C) 2026
 * Licensed under GPL-3.0 | See git history for contributors
 */

package com.music.vivi.playback

/**
 * Turns the download folder structure template into sanitised path segments, and composes the file name
 * for an export.
 *
 * Deliberately pure Kotlin with no Android or database imports: these are the rules that decide where a
 * file lands on disk, including the traversal safety, so they are unit-tested directly.
 */
object FolderTemplate {

    /** Organise downloads by artist and album unless the user says otherwise. */
    const val DEFAULT_TEMPLATE = "%artist%/%album%"

    /** A pathological template must not be able to build an unbounded tree. */
    const val MAX_SEGMENTS = 6

    /** Filesystems cap a single name at 255 bytes; leave room for the extension. */
    const val MAX_SEGMENT_BYTES = 200

    /** The same budget applies to a composed file name. */
    const val MAX_FILE_NAME_BYTES = 200

    const val DEFAULT_MIME_TYPE = "audio/mp4"

    /** Tokens offered as chips in the editor, in display order. */
    val TOKENS = listOf("%artist%", "%album%", "%year%", "%title%", "%songId%", "%quality%")

    private val SUPPORTED = setOf("artist", "album", "year", "title", "songid", "quality")
    private val TOKEN_PATTERN = Regex("%([A-Za-z]+)%")
    private val INVALID_CHARS = Regex("[\\\\/:*?\"<>|]")
    private val WHITESPACE = Regex("\\s+")

    private const val UNKNOWN_ARTIST = "Unknown Artist"
    private const val UNKNOWN_ALBUM = "Unknown Album"
    private const val UNKNOWN_YEAR = "Unknown Year"
    private const val UNKNOWN_QUALITY = "Unknown Quality"

    /** The metadata a template can resolve, decoupled from the database entities. */
    data class Input(
        val songId: String,
        val title: String?,
        val artists: List<String>,
        val album: String?,
        val year: Int?,
        val bitrate: Int?,
    )

    /** Validation outcome for the settings editor. */
    data class ParseResult(
        val unknownTokens: List<String>,
        val tooDeep: Boolean,
    ) {
        val isValid: Boolean get() = unknownTokens.isEmpty()
    }

    /** Reports tokens the app cannot resolve, plus whether the template is deeper than [MAX_SEGMENTS]. */
    fun parse(template: String): ParseResult {
        val segments = normalise(template)
        val unknown = segments
            .flatMap { segment -> TOKEN_PATTERN.findAll(segment).map { it.groupValues[1].lowercase() } }
            .filterNot { it in SUPPORTED }
            .distinct()
        return ParseResult(unknown, segments.count { it.isNotBlank() } > MAX_SEGMENTS)
    }

    /** Backslash is a path separator too, so a Windows-style template behaves the same. */
    private fun normalise(template: String): List<String> = template.replace('\\', '/').split('/')
}
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
/tmp/ktool/run-folder-template-tests.sh
```

Expected: `OK (4 tests)`.

- [ ] **Step 6: Commit**

```bash
cd /data/clones/clone-vivizzz007-vivi-music
git add app/build.gradle.kts \
  app/src/main/kotlin/com/music/vivi/playback/FolderTemplate.kt \
  app/src/test/kotlin/com/music/vivi/playback/FolderTemplateTest.kt
git commit -m "feat(downloads): add folder template parsing and a unit test source set"
```

---

## Task 2: `expand` — token resolution

**Files:**

- Modify: `app/src/test/kotlin/com/music/vivi/playback/FolderTemplateTest.kt`
- Modify: `app/src/main/kotlin/com/music/vivi/playback/FolderTemplate.kt`

- [ ] **Step 1: Write the failing tests**

Add to `FolderTemplateTest`:

```kotlin
    @Test
    fun `artist and album become segments`() {
        assertEquals(
            listOf("Metallica", "Master Of Puppets"),
            FolderTemplate.expand(input(), "%artist%/%album%"),
        )
    }

    @Test
    fun `every supported token resolves`() {
        assertEquals(
            listOf("Metallica", "Master Of Puppets", "1986", "Enter Sandman", "dQw4w9WgXcQ", "256kbps"),
            FolderTemplate.expand(input(), "%artist%/%album%/%year%/%title%/%songId%/%quality%"),
        )
    }

    @Test
    fun `tokens are case insensitive when expanding`() {
        assertEquals(listOf("Metallica"), FolderTemplate.expand(input(), "%ARTIST%"))
    }

    @Test
    fun `unknown token is kept literally`() {
        assertEquals(listOf("%genre%"), FolderTemplate.expand(input(), "%genre%"))
    }

    @Test
    fun `missing artist falls back`() {
        assertEquals(listOf("Unknown Artist"), FolderTemplate.expand(input(artists = emptyList()), "%artist%"))
    }

    @Test
    fun `missing album falls back`() {
        assertEquals(listOf("Unknown Album"), FolderTemplate.expand(input(album = null), "%album%"))
    }

    @Test
    fun `missing year falls back`() {
        assertEquals(listOf("Unknown Year"), FolderTemplate.expand(input(year = null), "%year%"))
    }

    @Test
    fun `missing bitrate falls back`() {
        assertEquals(listOf("Unknown Quality"), FolderTemplate.expand(input(bitrate = null), "%quality%"))
        assertEquals(listOf("Unknown Quality"), FolderTemplate.expand(input(bitrate = 0), "%quality%"))
    }

    @Test
    fun `blank title falls back to the song id`() {
        assertEquals(listOf("dQw4w9WgXcQ"), FolderTemplate.expand(input(title = "  "), "%title%"))
    }

    @Test
    fun `multiple artists are joined`() {
        assertEquals(
            listOf("Metallica, Jason Newsted"),
            FolderTemplate.expand(input(artists = listOf("Metallica", "Jason Newsted")), "%artist%"),
        )
    }

    @Test
    fun `backslash separates segments`() {
        assertEquals(
            listOf("Metallica", "Master Of Puppets"),
            FolderTemplate.expand(input(), "%artist%\\%album%"),
        )
    }
```

Note: the empty-template and `AC/DC` cases belong to Task 3 -- the temporary identity
`sanitizeSegment` added below cannot satisfy them yet, and Task 2 must end green.

- [ ] **Step 2: Run the tests to verify they fail**

```bash
/tmp/ktool/run-folder-template-tests.sh
```

Expected: FAIL — `error: unresolved reference: expand`.

- [ ] **Step 3: Implement `expand` and `resolve`**

In `FolderTemplate.kt`, add these two functions after `parse` (and keep `normalise` below them):

```kotlin
    /** Resolves [template] into the folder segments to create below the download root. */
    fun expand(input: Input, template: String): List<String> = normalise(template)
        .map { segment -> TOKEN_PATTERN.replace(segment) { resolve(it.groupValues[1].lowercase(), input) } }
        .map(::sanitizeSegment)
        .filter { it.isNotEmpty() }
        .take(MAX_SEGMENTS)

    private fun resolve(token: String, input: Input): String = when (token) {
        "artist" -> input.artists.joinToString(", ").ifBlank { UNKNOWN_ARTIST }
        "album" -> input.album.orEmpty().ifBlank { UNKNOWN_ALBUM }
        "year" -> input.year?.toString() ?: UNKNOWN_YEAR
        "title" -> input.title.orEmpty().ifBlank { input.songId }
        "songid" -> input.songId
        "quality" -> input.bitrate?.takeIf { it > 0 }?.let { "${it / 1000}kbps" } ?: UNKNOWN_QUALITY
        else -> "%$token%"
    }
```

Add a temporary `sanitizeSegment` so this task compiles (Task 3 replaces its body):

```kotlin
    internal fun sanitizeSegment(segment: String): String = segment
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
/tmp/ktool/run-folder-template-tests.sh
```

Expected: `OK (15 tests)`.

- [ ] **Step 5: Commit**

```bash
cd /data/clones/clone-vivizzz007-vivi-music
git add app/src/main/kotlin/com/music/vivi/playback/FolderTemplate.kt \
  app/src/test/kotlin/com/music/vivi/playback/FolderTemplateTest.kt
git commit -m "feat(downloads): resolve template tokens with fixed fallbacks"
```

---

## Task 3: Sanitising, traversal safety and caps

**Files:**

- Modify: `app/src/test/kotlin/com/music/vivi/playback/FolderTemplateTest.kt`
- Modify: `app/src/main/kotlin/com/music/vivi/playback/FolderTemplate.kt`

- [ ] **Step 1: Write the failing tests**

Add to `FolderTemplateTest`:

```kotlin
    @Test
    fun `empty template produces no segments`() {
        assertTrue(FolderTemplate.expand(input(), "").isEmpty())
        assertTrue(FolderTemplate.expand(input(), "  /  ").isEmpty())
    }

    @Test
    fun `a slash inside a resolved value stays in one segment`() {
        assertEquals(listOf("AC_DC"), FolderTemplate.expand(input(artists = listOf("AC/DC")), "%artist%"))
    }

    @Test
    fun `dots only segment is dropped`() {
        assertTrue(FolderTemplate.expand(input(title = ".."), "%title%").isEmpty())
        assertTrue(FolderTemplate.expand(input(title = "."), "%title%").isEmpty())
    }

    @Test
    fun `absolute looking template stays relative`() {
        assertEquals(listOf("etc", "Metallica"), FolderTemplate.expand(input(), "/etc/%artist%"))
    }

    @Test
    fun `trailing dots and spaces are stripped`() {
        assertEquals(listOf("Metallica"), FolderTemplate.expand(input(artists = listOf("Metallica. ")), "%artist%"))
    }

    @Test
    fun `invalid characters are replaced`() {
        assertEquals(
            listOf("a_b_c_d_e_f_g_h_i"),
            FolderTemplate.expand(input(artists = listOf("a/b:c*d?e\"f<g>h|i")), "%artist%"),
        )
    }

    @Test
    fun `whitespace is collapsed`() {
        assertEquals(listOf("The Band"), FolderTemplate.expand(input(artists = listOf("The    Band")), "%artist%"))
    }

    @Test
    fun `segments are capped at six`() {
        val template = (1..8).joinToString("/") { "%artist%" }
        assertEquals(6, FolderTemplate.expand(input(), template).size)
    }

    @Test
    fun `segments are capped at 200 bytes`() {
        val segment = FolderTemplate.expand(input(artists = listOf("ア".repeat(300))), "%artist%").single()
        assertTrue(segment.toByteArray(Charsets.UTF_8).size <= 200)
    }

    @Test
    fun `a dot file name is still allowed`() {
        assertEquals(listOf(".nomedia"), FolderTemplate.expand(input(title = ".nomedia"), "%title%"))
    }
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
/tmp/ktool/run-folder-template-tests.sh
```

Expected: FAIL on `empty template produces no segments`, `a slash inside a resolved value stays in one
segment`, `dots only segment is dropped`, `trailing dots and spaces are stripped`, `invalid
characters are replaced`, `whitespace is collapsed` and `segments are capped at 200 bytes`.

- [ ] **Step 3: Implement the real sanitising and truncation**

In `FolderTemplate.kt`, replace the temporary `sanitizeSegment` with:

```kotlin
    /**
     * One path segment, safe to use as a folder or file name: separators and other invalid characters
     * become `_`, whitespace collapses, trailing dots and spaces go (invalid on FAT/exFAT), and a segment
     * that is empty or only dots is dropped - which is what makes `..` impossible as a segment.
     */
    internal fun sanitizeSegment(segment: String): String {
        val cleaned = segment
            .replace(INVALID_CHARS, "_")
            .replace(WHITESPACE, " ")
            .trim()
            .trimEnd('.', ' ')
        if (cleaned.isEmpty() || cleaned.all { it == '.' }) return ""
        return truncateToBytes(cleaned, MAX_SEGMENT_BYTES)
    }

    /** Filesystems limit a name to 255 bytes, not characters: a CJK title is three times its length. */
    internal fun truncateToBytes(name: String, maxBytes: Int): String {
        if (name.toByteArray(Charsets.UTF_8).size <= maxBytes) return name
        var end = name.length
        while (end > 0 && name.substring(0, end).toByteArray(Charsets.UTF_8).size > maxBytes) end--
        val truncated = name.substring(0, end)
        return if (truncated.isNotEmpty() && truncated.last().isHighSurrogate()) truncated.dropLast(1) else truncated
    }
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
/tmp/ktool/run-folder-template-tests.sh
```

Expected: `OK (25 tests)`.

- [ ] **Step 5: Commit**

```bash
cd /data/clones/clone-vivizzz007-vivi-music
git add app/src/main/kotlin/com/music/vivi/playback/FolderTemplate.kt \
  app/src/test/kotlin/com/music/vivi/playback/FolderTemplateTest.kt
git commit -m "feat(downloads): sanitise template segments and cap depth and byte length"
```

---

## Task 4: `fileName` moves into `FolderTemplate`

**Files:**

- Modify: `app/src/test/kotlin/com/music/vivi/playback/FolderTemplateTest.kt`
- Modify: `app/src/main/kotlin/com/music/vivi/playback/FolderTemplate.kt`
- Modify: `app/src/main/kotlin/com/music/vivi/playback/DownloadFolderExporter.kt` (remove
  `buildFileName`, `extensionFor`, `sanitizeFileName`, `truncateToBytes` and their constants)

- [ ] **Step 1: Write the failing tests**

Add to `FolderTemplateTest`:

```kotlin
    @Test
    fun `file name keeps the artist title shape`() {
        assertEquals("Metallica - Enter Sandman.m4a", FolderTemplate.fileName(input(), "audio/mp4"))
    }

    @Test
    fun `file name extension follows the mime type`() {
        assertEquals("Metallica - Enter Sandman.webm", FolderTemplate.fileName(input(), "audio/webm; codecs=opus"))
        assertEquals("Metallica - Enter Sandman.mp3", FolderTemplate.fileName(input(), "audio/mpeg"))
        assertEquals("Metallica - Enter Sandman.ogg", FolderTemplate.fileName(input(), "audio/ogg"))
        assertEquals("Metallica - Enter Sandman.flac", FolderTemplate.fileName(input(), "audio/flac"))
        assertEquals("Metallica - Enter Sandman.m4a", FolderTemplate.fileName(input(), null))
    }

    @Test
    fun `file name falls back to the song id for a blank title`() {
        assertEquals("Metallica - dQw4w9WgXcQ.m4a", FolderTemplate.fileName(input(title = " "), "audio/mp4"))
    }

    @Test
    fun `file name stays inside the byte budget`() {
        val name = FolderTemplate.fileName(input(artists = listOf("ア".repeat(200))), "audio/mp4")
        assertTrue(name.toByteArray(Charsets.UTF_8).size <= 200)
    }
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
/tmp/ktool/run-folder-template-tests.sh
```

Expected: FAIL — `error: unresolved reference: fileName`.

- [ ] **Step 3: Implement `fileName` and `extensionFor`**

In `FolderTemplate.kt`, add after `expand`:

```kotlin
    /** `Artist - Title.ext`, the name the exporter has always written. */
    fun fileName(input: Input, mimeType: String?): String {
        val extension = extensionFor(mimeType)
        val artist = input.artists.joinToString(", ").ifBlank { UNKNOWN_ARTIST }
        val title = input.title.orEmpty().ifBlank { input.songId }
        val base = truncateToBytes(
            sanitizeSegment("$artist - $title"),
            MAX_FILE_NAME_BYTES - extension.length,
        ).trimEnd('.', ' ')
        return "${base.ifBlank { input.songId }}$extension"
    }

    internal fun extensionFor(mimeType: String?): String {
        val type = mimeType.orEmpty().substringBefore(';').trim().ifEmpty { DEFAULT_MIME_TYPE }
        return when {
            type.contains("webm") -> ".webm"
            type.contains("mp4") || type.contains("aac") -> ".m4a"
            type.contains("mpeg") -> ".mp3"
            type.contains("opus") -> ".opus"
            type.contains("ogg") -> ".ogg"
            type.contains("flac") -> ".flac"
            else -> ".m4a"
        }
    }
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
/tmp/ktool/run-folder-template-tests.sh
```

Expected: `OK (29 tests)`.

- [ ] **Step 5: Delete the now-duplicated naming code from the exporter**

In `DownloadFolderExporter.kt`:

1. Delete the private functions `buildFileName`, `extensionFor`, `sanitizeFileName` and
`truncateToBytes` (currently lines 352-387).
2. In the companion object (line 389), delete `DEFAULT_MIME_TYPE`, `UNKNOWN_ARTIST`,
`MAX_NAME_BYTES`, `INVALID_FILE_CHARS` and `WHITESPACE`. Keep `TAG`, `SUBFOLDER`,
`OPEN_MODE_TRUNCATE`, `PART_SUFFIX`, `BUFFER_SIZE`, `MAGIC_SIZE` and `EBML`.
3. In `exportLocked`, replace the naming lines with calls to the new unit (the `write` signature
changes in Task 5, so for now keep the existing one):

```kotlin
            val mimeType = sniffMimeType(songId)
                ?: song.format?.mimeType.orEmpty().substringBefore(';').trim()
                    .ifEmpty { FolderTemplate.DEFAULT_MIME_TYPE }
            val fileName = FolderTemplate.fileName(song.toTemplateInput(), mimeType)
```

1. Add this top-level mapping at the end of `DownloadFolderExporter.kt` (after the class, so
`FolderTemplate` stays free of database types):

```kotlin
/** Maps a library row onto the metadata the template can resolve. */
internal fun Song.toTemplateInput() = FolderTemplate.Input(
    songId = id,
    title = song.title,
    artists = artists.map { it.name },
    album = album?.title ?: song.albumName,
    year = song.year ?: album?.year,
    bitrate = format?.bitrate,
)
```

- [ ] **Step 6: Verify no stale references remain**

```bash
cd /data/clones/clone-vivizzz007-vivi-music
grep -n "buildFileName\|sanitizeFileName\|MAX_NAME_BYTES\|INVALID_FILE_CHARS" \
  app/src/main/kotlin/com/music/vivi/playback/DownloadFolderExporter.kt
```

Expected: no output.

- [ ] **Step 7: Commit**

```bash
cd /data/clones/clone-vivizzz007-vivi-music
git add app/src/main/kotlin/com/music/vivi/playback/FolderTemplate.kt \
  app/src/main/kotlin/com/music/vivi/playback/DownloadFolderExporter.kt \
  app/src/test/kotlin/com/music/vivi/playback/FolderTemplateTest.kt
git commit -m "refactor(downloads): move file-name composition into FolderTemplate"
```

---

## Task 5: Exporter writes through the template (MediaStore and app directory)

**Files:**

- Modify: `app/src/main/kotlin/com/music/vivi/playback/LocalDownloadPrefs.kt`
- Modify: `app/src/main/kotlin/com/music/vivi/playback/DownloadFolderExporter.kt`

- [ ] **Step 1: Add the preference key**

In `LocalDownloadPrefs.kt`, after `DownloadFolderUriKey`:

```kotlin
/** Folder structure template such as `%artist%/%album%`; empty means flat. */
val DownloadFolderTemplateKey = stringPreferencesKey("downloadFolderTemplate")
```

- [ ] **Step 2: Read the template and pass segments through the writers**

In `DownloadFolderExporter.kt`:

1. In `exportLocked`, immediately before `try {`, add:

```kotlin
        val template = context.dataStore[DownloadFolderTemplateKey] ?: FolderTemplate.DEFAULT_TEMPLATE
```

1. Inside the same `try`, replace the `write(songId, fileName, mimeType)` call with:

```kotlin
            val segments = FolderTemplate.expand(song.toTemplateInput(), template)
            write(songId, fileName, mimeType, segments)
```

1. Change the four signatures and their call sites to carry the segments:

```kotlin
    private fun write(songId: String, fileName: String, mimeType: String, segments: List<String>) {
```

```kotlin
    private fun writeToDocumentTree(
        treeUri: Uri,
        songId: String,
        fileName: String,
        mimeType: String,
        segments: List<String>,
    ) {
```

```kotlin
    private fun writeToPublicMusic(
        songId: String,
        fileName: String,
        mimeType: String,
        segments: List<String>,
    ) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.Q) {
            writeToAppSpecificMusicDir(songId, fileName, segments)
        } else {
            writeViaMediaStore(songId, fileName, mimeType, segments)
        }
    }
```

```kotlin
    private fun writeViaMediaStore(
        songId: String,
        fileName: String,
        mimeType: String,
        segments: List<String>,
    ) {
```

1. In `writeViaMediaStore`, replace the `relativePath` line with:

```kotlin
        val relativePath = buildString {
            append(Environment.DIRECTORY_MUSIC).append('/').append(SUBFOLDER)
            segments.forEach { append('/').append(it) }
        }
```

`deleteOwnExports(resolver, collection, fileName, relativePath)` already takes the path, so a
re-download replaces the file in the new location with no further change.

1. In `writeToAppSpecificMusicDir`, change the signature to `(songId: String, fileName: String,
segments: List<String>)` and replace the directory line with:

```kotlin
        val directory = File(base ?: context.filesDir, (listOf(SUBFOLDER) + segments).joinToString("/"))
```

- [ ] **Step 3: Compile-check what can be checked locally**

```bash
cd /data/clones/clone-vivizzz007-vivi-music
/tmp/ktool/run-folder-template-tests.sh
```

Expected: `OK (29 tests)` (unchanged — the exporter is not part of the pure unit) and no
unresolved-reference errors from kotlinc for `FolderTemplate.kt`.

- [ ] **Step 4: Verify the MediaStore path logic by inspection**

```bash
grep -n "relativePath\|deleteOwnExports(" app/src/main/kotlin/com/music/vivi/playback/DownloadFolderExporter.kt
```

Expected: `relativePath` is built once in `writeViaMediaStore` and passed to `deleteOwnExports`; the
cleanup query still appends the trailing `/` (`"$relativePath/"`).

- [ ] **Step 5: Commit**

```bash
cd /data/clones/clone-vivizzz007-vivi-music
git add app/src/main/kotlin/com/music/vivi/playback/LocalDownloadPrefs.kt \
  app/src/main/kotlin/com/music/vivi/playback/DownloadFolderExporter.kt
git commit -m "feat(downloads): write exports into the templated subfolders"
```

---

## Task 6: Nested directories for the SAF root

**Files:**

- Modify: `app/src/main/kotlin/com/music/vivi/playback/SafFolders.kt`
- Modify: `app/src/main/kotlin/com/music/vivi/playback/DownloadFolderExporter.kt`

- [ ] **Step 1: Generalise `findFile` and `createFile`, and add `resolveDirectory`**

In `SafFolders.kt`, replace the existing `findFile`, `createFile` and `childrenUri` with the
following (the file already has `displayName`, `rename`, `delete`, `documentUri` and `query`, which
stay):

```kotlin
    /**
     * Walks [segments] below the tree root, creating the directories that are missing, and returns the
     * deepest directory it could reach.
     *
     * A name that already exists as a file stops the walk rather than creating a "Name (1)" directory
     * beside it, so the export lands one level up instead.
     */
    fun resolveDirectory(context: Context, treeUri: Uri, segments: List<String>): Uri {
        var parent = documentUri(treeUri)
        for (segment in segments) {
            val existing = findFile(context, treeUri, parent, segment)
            val next = when {
                existing == null -> createDirectory(context, parent, segment)
                isDirectory(context, existing) -> existing
                else -> null
            }
            if (next == null) return parent
            parent = next
        }
        return parent
    }

    /** URI of the child called [displayName] directly inside [parent], or null when there is none. */
    fun findFile(context: Context, treeUri: Uri, parent: Uri, displayName: String): Uri? = runCatching {
        query(
            context,
            DocumentsContract.buildChildDocumentsUriUsingTree(
                treeUri,
                DocumentsContract.getDocumentId(parent),
            ),
            arrayOf(
                DocumentsContract.Document.COLUMN_DOCUMENT_ID,
                DocumentsContract.Document.COLUMN_DISPLAY_NAME,
            ),
        ) { cursor ->
            var match: Uri? = null
            // query() has already positioned the cursor on the first row, so start there.
            do {
                if (cursor.getString(1) == displayName) {
                    match = DocumentsContract.buildDocumentUriUsingTree(treeUri, cursor.getString(0))
                    break
                }
            } while (cursor.moveToNext())
            match
        }
    }.getOrNull()

    /** Creates a file called [displayName] directly inside [parent], or null when the folder refuses. */
    fun createFile(context: Context, parent: Uri, mimeType: String, displayName: String): Uri? =
        runCatching {
            DocumentsContract.createDocument(context.contentResolver, parent, mimeType, displayName)
        }.getOrNull()

    private fun createDirectory(context: Context, parent: Uri, displayName: String): Uri? =
        runCatching {
            DocumentsContract.createDocument(
                context.contentResolver,
                parent,
                DocumentsContract.Document.MIME_TYPE_DIR,
                displayName,
            )
        }.getOrNull()

    private fun isDirectory(context: Context, uri: Uri): Boolean =
        query(context, uri, arrayOf(DocumentsContract.Document.COLUMN_MIME_TYPE)) { cursor ->
            cursor.getString(0) == DocumentsContract.Document.MIME_TYPE_DIR
        } ?: false
```

- [ ] **Step 2: Point the exporter's SAF writer at the resolved directory**

In `DownloadFolderExporter.kt`, inside `writeToDocumentTree`, replace the first three lines (the
`existing` lookup, the `target` choice and the `createFile` call) with:

```kotlin
        val directory = SafFolders.resolveDirectory(context, treeUri, segments)
        val existing = SafFolders.findFile(context, treeUri, directory, fileName)
        val target = if (existing == null) fileName else "$fileName$PART_SUFFIX"
        val uri = SafFolders.createFile(context, directory, mimeType, target)
            ?: throw IOException("Could not create $target in $directory")
```

- [ ] **Step 3: Verify no stale call sites remain**

```bash
cd /data/clones/clone-vivizzz007-vivi-music
grep -rn "SafFolders.findFile\|SafFolders.createFile\|childrenUri" \
  app/src/main/kotlin/com/music/vivi/
```

Expected: exactly two hits, both in `DownloadFolderExporter.writeToDocumentTree` (the `findFile` and
`createFile` calls above). No `childrenUri` hits.

- [ ] **Step 4: Commit**

```bash
cd /data/clones/clone-vivizzz007-vivi-music
git add app/src/main/kotlin/com/music/vivi/playback/SafFolders.kt \
  app/src/main/kotlin/com/music/vivi/playback/DownloadFolderExporter.kt
git commit -m "feat(downloads): create nested directories in the picked SAF folder"
```

---

## Task 7: Settings row and editor dialog

**Files:**

- Modify: `app/src/main/res/values/local_download_strings.xml`
- Modify: `app/src/main/kotlin/com/music/vivi/ui/screens/settings/LocalDownloadSettings.kt`

- [ ] **Step 1: Add the strings**

In `local_download_strings.xml`, before `</resources>`:

```xml
    <string name="download_folder_structure">Folder structure</string>
    <string name="download_folder_structure_flat">Flat - save directly in the chosen folder</string>
    <string name="download_folder_structure_hint">Use the tokens below, separated by /. Leave empty to save directly in the chosen folder.</string>
    <string name="download_folder_structure_preview">Preview</string>
    <string name="download_folder_structure_unknown_token">Unknown token: %1$s</string>
    <string name="download_folder_structure_too_deep">Only the first 6 folders are used</string>
    <string name="download_folder_default_root">Music/Vivi</string>
```

- [ ] **Step 2: Add the row and the dialog**

In `LocalDownloadSettings.kt`, add these imports:

```kotlin
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.AssistChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.TextRange
import androidx.compose.ui.text.input.TextFieldValue
import androidx.compose.ui.unit.dp
import com.music.vivi.LocalDatabase
import com.music.vivi.playback.DownloadFolderTemplateKey
import com.music.vivi.playback.FolderTemplate
import com.music.vivi.playback.toTemplateInput
import com.music.vivi.ui.component.ActionPromptDialog
import com.music.vivi.db.entities.Song
import kotlinx.coroutines.flow.first
```

At the top of `LocalDownloadSettingsGroup`, add:

```kotlin
    val database = LocalDatabase.current
    val (template, onTemplateChange) =
        rememberPreference(DownloadFolderTemplateKey, FolderTemplate.DEFAULT_TEMPLATE)
    var editingTemplate by remember { mutableStateOf(false) }
    var sampleSong by remember { mutableStateOf<Song?>(null) }

    // A real downloaded song makes the preview honest; the library may be empty.
    LaunchedEffect(Unit) {
        sampleSong = withContext(Dispatchers.IO) {
            database.downloadedSongsByCreateDateAsc().first().lastOrNull()
        }
    }
```

Inside `buildList`, after the "Choose folder" item, add:

```kotlin
                add(
                    Material3SettingsItem(
                        icon = painterResource(R.drawable.list),
                        title = { Text(stringResource(R.string.download_folder_structure)) },
                        description = {
                            Text(
                                text = template.ifBlank {
                                    stringResource(R.string.download_folder_structure_flat)
                                },
                            )
                        },
                        onClick = { editingTemplate = true },
                    ),
                )
```

After the `ExpressiveSettingGroup(...)` call, add:

```kotlin
    if (editingTemplate) {
        FolderStructureDialog(
            template = template,
            rootLabel = folderName ?: stringResource(R.string.download_folder_default_root),
            sampleSong = sampleSong,
            onDismiss = { editingTemplate = false },
            onSave = {
                onTemplateChange(it)
                editingTemplate = false
            },
        )
    }
```

At the end of the file, before `private const val TAG`, add:

```kotlin
@Composable
private fun FolderStructureDialog(
    template: String,
    rootLabel: String,
    sampleSong: Song?,
    onDismiss: () -> Unit,
    onSave: (String) -> Unit,
) {
    var draft by remember { mutableStateOf(TextFieldValue(template)) }
    val result = FolderTemplate.parse(draft.text)

    // The example keeps the preview meaningful on a fresh install with nothing downloaded yet.
    val example = FolderTemplate.Input(
        songId = "dQw4w9WgXcQ",
        title = "Enter Sandman",
        artists = listOf("Metallica"),
        album = "Master Of Puppets",
        year = 1986,
        bitrate = 256_000,
    )
    val previewInput = sampleSong?.toTemplateInput() ?: example
    val previewName = FolderTemplate.fileName(previewInput, sampleSong?.format?.mimeType)
    val preview = (listOf(rootLabel) + FolderTemplate.expand(previewInput, draft.text) + previewName)
        .joinToString("/")

    ActionPromptDialog(
        title = stringResource(R.string.download_folder_structure),
        onDismiss = onDismiss,
        onConfirm = { if (result.isValid) onSave(draft.text) },
        onReset = { draft = TextFieldValue(FolderTemplate.DEFAULT_TEMPLATE) },
        onCancel = onDismiss,
    ) {
        OutlinedTextField(
            value = draft,
            onValueChange = { draft = it },
            modifier = Modifier.fillMaxWidth(),
            singleLine = true,
            isError = !result.isValid,
            label = { Text(stringResource(R.string.download_folder_structure)) },
        )
        if (result.unknownTokens.isNotEmpty()) {
            Text(
                text = stringResource(
                    R.string.download_folder_structure_unknown_token,
                    result.unknownTokens.joinToString(", ") { "%$it%" },
                ),
                color = MaterialTheme.colorScheme.error,
                style = MaterialTheme.typography.bodySmall,
            )
        } else if (result.tooDeep) {
            Text(
                text = stringResource(R.string.download_folder_structure_too_deep),
                style = MaterialTheme.typography.bodySmall,
            )
        }
        FlowRow(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            FolderTemplate.TOKENS.forEach { token ->
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
                text = stringResource(R.string.download_folder_structure_hint),
                modifier = Modifier.padding(top = 8.dp),
                style = MaterialTheme.typography.bodySmall,
            )
        }
    }
}

private fun TextFieldValue.insertAtCursor(text: String): TextFieldValue {
    val start = selection.start.coerceAtLeast(0)
    val end = selection.end.coerceAtLeast(0)
    return copy(
        text = this.text.replaceRange(start, end, text),
        selection = TextRange(start + text.length),
    )
}
```

- [ ] **Step 3: Check for accidental duplicate strings**

```bash
cd /data/clones/clone-vivizzz007-vivi-music
for name in download_folder_structure download_folder_structure_flat download_folder_structure_hint \
            download_folder_structure_preview download_folder_structure_unknown_token \
            download_folder_structure_too_deep download_folder_default_root; do
  printf '%-46s %s\n' "$name" "$(grep -rl "name=\"$name\"" app/src/main/res/values/ | tr '\n' ' ')"
done
```

Expected: each name appears exactly once, in `local_download_strings.xml` only.

- [ ] **Step 4: Commit**

```bash
cd /data/clones/clone-vivizzz007-vivi-music
git add app/src/main/res/values/local_download_strings.xml \
  app/src/main/kotlin/com/music/vivi/ui/screens/settings/LocalDownloadSettings.kt
git commit -m "feat(downloads): add a folder structure editor with token chips and preview"
```

---

## Task 8: Delivery — CI tests, patch, fork push, on-device build

**Files:**

- Modify: `/tmp/vivi-fork/.github/workflows/local-build.yml` *(fork only)*
- Modify: `/tmp/vivi-fork/local-patches/README.md` *(fork only)*
- Regenerate: `/tmp/vivi-fork/local-patches/01-download-folder.patch` *(fork only)*

- [ ] **Step 1: Make CI run the unit tests**

In `/tmp/vivi-fork/.github/workflows/local-build.yml`, add this step directly after the `Build APK` step:

```yaml
      - name: Run unit tests
        working-directory: src
        run: |
          set -euo pipefail
          ./gradlew --console=plain --no-configuration-cache \
            "test${{ steps.inputs.outputs.variant }}UnitTest"
```

(`steps.inputs.outputs.variant` is `UniversalFossDebug`, so this resolves to `testUniversalFossDebugUnitTest`.)

- [ ] **Step 2: Regenerate the patch and verify it applies to pristine upstream**

```bash
cd /data/clones/clone-vivizzz007-vivi-music
git diff main..local/download-folder -- app/ > /tmp/01-download-folder.patch
git diff --numstat main..local/download-folder -- app/ | tail -3
git worktree list
rm -rf /tmp/vivi-verify && git worktree prune
git worktree add --detach --quiet /tmp/vivi-verify main
cd /tmp/vivi-verify && git apply --check --verbose /tmp/01-download-folder.patch && echo "APPLY CHECK OK"
```

Expected: `APPLY CHECK OK`, and the numstat shows the five new files plus the two hook files and
`app/build.gradle.kts`. Nothing under `docs/` may appear.

- [ ] **Step 3: Update the fork README**

In `/tmp/vivi-fork/local-patches/README.md`:

1. In "What patch 01 does", add:

```markdown
- Optional folder structure template (default `%artist%/%album%`) applied under whichever root is
  active, with `%artist%`, `%album%`, `%year%`, `%title%`, `%songId%` and `%quality%` tokens, edited in
  *Settings -> Storage -> Folder structure*. An explicitly emptied template means flat.
```

1. In the limitations table, replace the "Same artist + title means one file" row with:

```markdown
| Same artist + title means one file | Two songs sharing artist and title map to the same name and the later export replaces the earlier one. Adding `%songId%` to the template avoids it. |
| Changing the template does not move existing files | Only new exports use the new structure; files already written stay where they are. |
```

1. Add to the on-device checklist: set `%artist%/%album%` and confirm nested folders under both
roots; clear the template and confirm flat output; press Reset and confirm the default returns;
confirm the preview line matches the folder a new download lands in.

- [ ] **Step 4: Commit and push the fork**

```bash
cd /tmp/vivi-fork
cp /tmp/01-download-folder.patch local-patches/01-download-folder.patch
git add -A
git -c user.name=binhex -c user.email=megalith01@gmail.com commit -m "local: templated download folder structure

Adds %artist%/%album% style subfolders under whichever download root is active,
defaulting to %artist%/%album%, with per-destination path handling and unit tests
for the sanitising and traversal rules. CI now runs the unit tests."
git -c credential.helper='!gh auth git-credential' push fork fork-main:main
```

- [ ] **Step 5: Watch CI to green**

```bash
sleep 30
gh run list --repo binhex/vivi-music --workflow local-build.yml --limit 3
RID=$(gh run list --repo binhex/vivi-music --workflow local-build.yml --limit 1 --json databaseId --jq '.[0].databaseId')
gh run view "$RID" --repo binhex/vivi-music
```

Expected: the `Run unit tests` step passes and the run ends green. On failure: `gh run view "$RID"
--repo binhex/vivi-music --log-failed`, fix in the clone, return to Step 2.

- [ ] **Step 6: Download and verify the APK**

```bash
cd /tmp && rm -rf vivi-apk3
gh run download "$RID" --repo binhex/vivi-music --dir /tmp/vivi-apk3
find /tmp/vivi-apk3 -name "*.apk" -exec ls -la {} \;
cd /tmp && rm -rf apk-x3 && mkdir apk-x3 && cd apk-x3
unzip -q -o /tmp/vivi-apk3/*/app-universal-foss-debug.apk "classes*.dex" "resources.arsc"
grep -a -l "FolderStructureDialog" classes*.dex
grep -a -c "download_folder_structure" resources.arsc
```

Expected: the APK exists, the dex contains `FolderStructureDialog`, and `resources.arsc` contains
the new strings. Tell the user the artifact name and that the previous debug build must be
uninstalled first (each CI run signs with a fresh debug keystore).

- [ ] **Step 7: Report and hand over for on-device testing**

Summarise: what changed, the CI run URL, the APK artifact name, and the on-device checklist from the
README. Do not claim the feature works on device — that is the user's verification.

---

## Self-review notes

- **Spec coverage:** every spec section maps to a task — grammar and resolution to Tasks 1-3,
  sanitising and traversal safety to Task 3, file naming to Task 4, destination handling to Tasks 5-6
  (MediaStore/app-dir and SAF), the editor and strings to Task 7, unit tests to Tasks 1-4, delivery
  and the README to Task 8. The spec's `expand(song, format, template)` signature is realised as
  `expand(input, template)` with a `Song.toTemplateInput()` mapping added in Task 4; this keeps
  `FolderTemplate` free of Room and Compose types so the unit tests need no Android classpath. The
  spec's `parse(template): ParseResult` is realised as `parse` returning `ParseResult(unknownTokens,
  tooDeep)`.
- **Placeholders:** none. Every code step contains the full code, every command has an expected result.
- **Type consistency:** `FolderTemplate.Input` fields (`songId`, `title`, `artists`, `album`, `year`,
  `bitrate`) are used identically in Tasks 2, 4, 5 and 7; `ParseResult` exposes `unknownTokens`,
  `tooDeep` and `isValid` in Tasks 1 and 7; `SafFolders.resolveDirectory`/`findFile`/`createFile`
  signatures in Task 6 match the call sites added in the same task; `FolderTemplate.fileName(input,
  mimeType)` takes a nullable mime type everywhere it is called.
- **Deliberate deviation:** the spec listed `buildFileName` as staying in the exporter; Task 4 moves
  it into `FolderTemplate` so the editor preview and the exporter share one naming rule (DRY), and so
  byte truncation is covered by tests.
