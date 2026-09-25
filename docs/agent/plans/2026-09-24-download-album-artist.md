# Album-Artist Folders for Downloaded Compilations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use sub-agents (recommended) to implement this plan
> task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A download taken from a various-artists album lands in one `<root>/Various Artists/<album>/` folder instead
of one folder per performer, while the file name keeps the real performer of each track.

**Architecture:** The folder template's `%artist%` gains a second, higher-priority source: an album-level artist. A
new pure unit decides that artist (`playback/AlbumArtist.kt`) from the library's credited album artists and its
per-track performers. `DownloadFormat.Input` carries it in a new `folderArtists` field that the folder branch consumes
and the file-name branch ignores. The exporter resolves it with three new `DatabaseDao` queries, best-effort, only
when the folder template actually uses `%artist%`. Everything ships inside `local-patches/01-download-folder.patch`,
so the fork stays upstream-edit-free.

**Tech Stack:** Kotlin 2.x, Jetpack Compose (Material 3), Room (DAO + projections), Kotlin coroutines, JUnit 4.13.2,
Kover 0.9.9 (95% line gate), Media3 download cache, Android SAF/MediaStore. Local verification uses a standalone
`kotlinc` + JUnit + JaCoCo harness in `/tmp/ktool` because this machine only has JDK 11 and no resolvable JUnit for
Gradle; the Gradle build, Android lint and the Kover gate run in CI (`.github/workflows/local-build.yml`, JDK 21).

---

## Scope check

Single subsystem. The spec (`docs/agent/specs/2026-09-24-download-album-artist-design.md`) changes one feature - how
the download folder template resolves its artist token - and no other subsystem is touched. No split into separate
plans is needed.

## Authoritative references

- Spec: `docs/agent/specs/2026-09-24-download-album-artist-design.md`
- Patch being extended: `local-patches/01-download-folder.patch`
- Fork rules: `local-patches/README.md`, `docs/agent/specs/2026-09-23-download-folder-structure-design.md` (Delivery
  section)

## How this fork is edited (read before Task 1)

The fork commits **no upstream file**. `app/` in this repository is a pristine copy of upstream
`vivizzz007/vivi-music`; the download-folder feature exists only as `local-patches/01-download-folder.patch`.
Therefore:

1. **All Kotlin edits happen in a throw-away checkout in `/tmp`** with patch 01 applied. Never edit `app/` in
   `/data/forks/vivi-music`; that tree must stay pristine so `git apply --check` keeps proving the patch applies to
   upstream.
2. **The deliverable is the regenerated patch file**, committed in `/data/forks/vivi-music` together with the
   `README.md` update.
3. **Commits:** frequent commits in the scratch checkout (Tasks 2-7), one final commit in the fork repository carrying
   the regenerated patch and the README (Task 8). This mirrors commit `e3d7a230 local: file-name template with track
   numbers (patch 01 update) (#1)`, where the patch file grew while no upstream file was committed.
4. Temp files and helper scripts live in `/tmp` and are never committed.

## File structure

| Path (inside the scratch checkout) | Action | Responsibility |
| --- | --- | --- |
| `app/src/main/kotlin/com/music/vivi/playback/AlbumArtist.kt` | Create | The pure album-artist rule: the `VARIOUS_ARTISTS` constant, the `AlbumPerformerTracks` Room projection, and `folderArtists(...)`. No Android imports, so it compiles and tests as plain JVM Kotlin. |
| `app/src/main/kotlin/com/music/vivi/playback/DownloadFormat.kt` | Modify | Pure path and name syntax. Gains the `folderArtists` input field, the `artistText` helper that applies it to the folder branch only, the `namedOrNull` guard, and `usesArtistToken`. |
| `app/src/main/kotlin/com/music/vivi/db/DatabaseDao.kt` | Modify (upstream hook) | Three suspend queries: credited album artists, per-performer song counts, album song count. |
| `app/src/main/kotlin/com/music/vivi/playback/DownloadFolderExporter.kt` | Modify | Resolves the album artist for one export through the shared `albumFolderArtists` helper and feeds it into `Input`. |
| `app/src/main/kotlin/com/music/vivi/ui/screens/settings/LocalDownloadSettings.kt` | Modify | Resolves the album artist for the preview sample so the dialog preview cannot disagree with the exporter, and shows one informational line about `%artist%`. |
| `app/src/main/res/values/local_download_strings.xml` | Modify | One new string for that line. |
| `app/build.gradle.kts` | Modify (upstream hook) | Adds `AlbumArtist*` to the Kover include filter and `AlbumArtistTest` to its excludes. |
| `app/src/test/kotlin/com/music/vivi/playback/AlbumArtistTest.kt` | Create | Rule and boundary tests for `folderArtists`. |
| `app/src/test/kotlin/com/music/vivi/playback/DownloadFormatTest.kt` | Modify | New cases for `folderArtists`, `usesArtistToken` and the tidy pass. |
| `/tmp/ktool/run-album-artist-tests.sh` | Create (temp) | Compiles the pure units plus both test classes with standalone `kotlinc` and runs JUnit. |
| `/tmp/ktool/check-album-artist-sql.py` | Create (temp) | Extracts the new queries from `DatabaseDao.kt`, builds the real tables in SQLite, and checks the rows they return. |

Nothing else changes. In particular `DownloadUtil.kt`, `SafFolders.kt`, `LocalDownloadPrefs.kt` and
`StorageSettings.kt` stay exactly as patch 01 left them.

## Verification summary (what can and cannot be checked locally)

| Check | Local | CI |
| --- | --- | --- |
| `AlbumArtistTest`, `DownloadFormatTest` | Yes - `kotlinc` harness, JUnit | Yes - `testUniversalFossDebugUnitTest` |
| Line coverage of `AlbumArtist*` and `DownloadFormat*` | Approximate - JaCoCo CSV in the harness | Authoritative - `koverVerify`, 95% line |
| The three SQL queries (table and column names, `order` keyword, grouped counts) | Yes - SQLite dry run | Yes - Room validates the DAO at compile time |
| `DatabaseDao.kt` compile, Android APIs, Compose, resources, string ids | **No** | Yes - `assembleUniversalFossDebug` + lint |
| Patch applies to pristine upstream `main` | Yes - `local-patches/apply.sh --check` | Yes - `Local Patch Build`, `Upstream Drift Check` |

Tasks 5 and 6 touch Android-dependent files and therefore have **no local compile check**; they are verified by
matching the exact snippets in this plan, by review, and by the CI gates above. Do not claim Tasks 5 or 6 are
"verified" beyond that.

---

### Task 1: Scratch checkout and a proven local test harness

**Files:**

- Create (temp): `/tmp/ktool/run-album-artist-tests.sh`
- Create: `/tmp/vivi-album-artist` (throw-away clone, not committed)

- [ ] **Step 1: Clone the fork and apply patch 01**

```bash
rm -rf /tmp/vivi-album-artist
git clone --no-hardlinks /data/forks/vivi-music /tmp/vivi-album-artist
cd /tmp/vivi-album-artist
git checkout -b local/album-artist
./local-patches/apply.sh
git status --short | head -20
```

Expected: `OK   01-download-folder.patch (applied)` and a status list containing modified `app/build.gradle.kts`,
`app/src/main/kotlin/com/music/vivi/db/DatabaseDao.kt`, `app/src/main/kotlin/com/music/vivi/playback/DownloadUtil.kt`,
`app/src/main/kotlin/com/music/vivi/ui/screens/settings/StorageSettings.kt`, plus untracked new files including
`app/src/main/kotlin/com/music/vivi/playback/DownloadFormat.kt`.

- [ ] **Step 2: Confirm the files this plan edits exist in the scratch checkout**

```bash
ls app/src/main/kotlin/com/music/vivi/playback/ | grep -E "Download|LocalDownloadPrefs|SafFolders"
ls app/src/test/kotlin/com/music/vivi/playback/
```

Expected: `DownloadFolderExporter.kt  DownloadFormat.kt  LocalDownloadPrefs.kt  SafFolders.kt` and
`DownloadFormatTest.kt`.

- [ ] **Step 3: Write the local test harness script (temp, never committed)**

Create `/tmp/ktool/run-album-artist-tests.sh`:

```bash
#!/usr/bin/env bash
# Compiles the pure download-format units and their tests with a standalone Kotlin compiler, then runs
# JUnit directly. This machine only has JDK 11 and no resolvable JUnit for Gradle, so the Gradle unit-test
# task cannot run here; CI is the authoritative gate. Usage: run-album-artist-tests.sh [repo-root]
set -euo pipefail

REPO="${1:-/tmp/vivi-album-artist}"
TOOL=/tmp/ktool
MAIN="$REPO/app/src/main/kotlin/com/music/vivi/playback"
TEST="$REPO/app/src/test/kotlin/com/music/vivi/playback"
OUT="$TOOL/album-artist-out"
STDLIB="$TOOL/kotlinc2310/kotlinc/lib/kotlin-stdlib.jar"
CP="$TOOL/junit.jar:$TOOL/hamcrest.jar"

rm -rf "$OUT" && mkdir -p "$OUT"

"$TOOL/kotlinc2310/kotlinc/bin/kotlinc" -nowarn -cp "$CP" -d "$OUT" \
  "$MAIN/AlbumArtist.kt" \
  "$MAIN/DownloadFormat.kt" \
  "$TEST/AlbumArtistTest.kt" \
  "$TEST/DownloadFormatTest.kt"

java -javaagent:"$TOOL/jacoco-agent.jar=destfile=$OUT/jacoco.exec" \
  -cp "$OUT:$CP:$STDLIB" \
  org.junit.runner.JUnitCore \
  com.music.vivi.playback.AlbumArtistTest \
  com.music.vivi.playback.DownloadFormatTest

java -jar "$TOOL/jacoco-cli.jar" report "$OUT/jacoco.exec" \
  --classfiles "$OUT" --sourcefiles "$MAIN" --csv "$OUT/jacoco.csv" --quiet

# Kover counts the main classes only and excludes the test classes, so mirror that here. Column 3 is CLASS,
# 8 is LINE_MISSED, 9 is LINE_COVERED.
awk -F, 'NR == 1 || $3 == "DownloadFormat" || $3 == "AlbumArtistKt" {
  printf "%-18s line coverage %s/%s\n", $3, $9, $8 + $9
}' "$OUT/jacoco.csv"
```

- [ ] **Step 4: Prove the harness works before changing any code**

Run the same toolchain against the files exactly as patch 01 left them. This is the baseline every later
task compares against, so record the number it prints.

```bash
chmod +x /tmp/ktool/run-album-artist-tests.sh
TOOL=/tmp/ktool
SRC=/tmp/vivi-album-artist/app/src/main/kotlin/com/music/vivi/playback
TEST=/tmp/vivi-album-artist/app/src/test/kotlin/com/music/vivi/playback
rm -rf "$TOOL/baseline-out" && mkdir -p "$TOOL/baseline-out"
"$TOOL/kotlinc2310/kotlinc/bin/kotlinc" -nowarn \
  -cp "$TOOL/junit.jar:$TOOL/hamcrest.jar" \
  -d "$TOOL/baseline-out" "$SRC/DownloadFormat.kt" "$TEST/DownloadFormatTest.kt"
java -cp "$TOOL/baseline-out:$TOOL/junit.jar:$TOOL/hamcrest.jar:$TOOL/kotlinc2310/kotlinc/lib/kotlin-stdlib.jar" \
  org.junit.runner.JUnitCore com.music.vivi.playback.DownloadFormatTest
```

Expected: `OK (<baseline> tests)` with no failures. In the previous checkout this file held 76 tests; if
the number you see differs, that is the baseline - later tasks expect the baseline plus the number of tests
they add, not a fixed figure.

- [ ] **Step 5: Write the SQL dry-run checker (temp, never committed)**

Create `/tmp/ktool/check-album-artist-sql.py`:

```python
#!/usr/bin/env python3
"""Runs the album-artist DAO queries against a real SQLite database.

The SQL is extracted from DatabaseDao.kt rather than retyped, so the check cannot drift from the DAO. The
tables are created from the DDL in MusicDatabase.kt's migrations, which is what Room creates.
"""
import re
import sqlite3
import sys

DAO = sys.argv[1]

DDL = """
CREATE TABLE song (id TEXT NOT NULL PRIMARY KEY, albumName TEXT);
CREATE TABLE artist (id TEXT NOT NULL PRIMARY KEY, name TEXT NOT NULL);
CREATE TABLE album (id TEXT NOT NULL PRIMARY KEY, title TEXT NOT NULL);
CREATE TABLE song_artist_map (songId TEXT NOT NULL, artistId TEXT NOT NULL, position INTEGER NOT NULL,
                              PRIMARY KEY(songId, artistId));
CREATE TABLE song_album_map (songId TEXT NOT NULL, albumId TEXT NOT NULL, `index` INTEGER,
                             PRIMARY KEY(songId, albumId));
CREATE TABLE album_artist_map (albumId TEXT NOT NULL, artistId TEXT NOT NULL, `order` INTEGER NOT NULL,
                               PRIMARY KEY(albumId, artistId));
"""

DATA = """
INSERT INTO album VALUES ('A1', 'QUEENDOM2 FINAL');
INSERT INTO artist VALUES
  ('VA', 'Various Artists'), ('ar1', 'HYOLYN'), ('ar2', 'WJSN'),
  ('ar3', 'Kep1er'), ('ar4', 'LOONA'), ('ar5', 'Brave Girls'), ('ar6', 'VIVIZ');
INSERT INTO album_artist_map VALUES ('A1', 'VA', 0);
INSERT INTO song VALUES ('s1', NULL), ('s2', NULL), ('s3', NULL), ('s4', NULL), ('s5', NULL), ('s6', NULL);
INSERT INTO song_album_map VALUES
  ('s1', 'A1', 0), ('s2', 'A1', 1), ('s3', 'A1', 2),
  ('s4', 'A1', 3), ('s5', 'A1', 4), ('s6', 'A1', 5);
INSERT INTO song_artist_map VALUES
  ('s1', 'ar1', 0), ('s2', 'ar2', 0), ('s3', 'ar3', 0),
  ('s4', 'ar4', 0), ('s5', 'ar5', 0), ('s6', 'ar6', 0);
"""

QUERY_BLOCK = re.compile(r'@Query\(\s*((?:"(?:[^"\\]|\\.)*"\s*\+?\s*)+),?\s*\)', re.S)
LITERAL = re.compile(r'"((?:[^"\\]|\\.)*)"')

source = open(DAO).read()
queries = ["".join(LITERAL.findall(block)) for block in QUERY_BLOCK.findall(source)]
credited = [q for q in queries if q.startswith("SELECT artist.name FROM album_artist_map")]
performers = [q for q in queries if q.startswith("SELECT artist.name AS artist, COUNT(DISTINCT song_album_map.songId)")]
counts = [q for q in queries if q.startswith("SELECT COUNT(DISTINCT songId) FROM song_album_map")]

assert len(credited) == 1, f"expected 1 credited-artists query, found {len(credited)}"
assert len(performers) == 1, f"expected 1 performer query, found {len(performers)}"
assert len(counts) == 1, f"expected 1 song-count query, found {len(counts)}"

db = sqlite3.connect(":memory:")
db.executescript(DDL)
db.executescript(DATA)


def run(sql):
    return db.execute(sql.replace(":albumId", "'A1'")).fetchall()


credited_rows = run(credited[0])
performer_rows = run(performers[0])
count_rows = run(counts[0])

assert credited_rows == [("Various Artists",)], credited_rows
assert sorted(performer_rows) == [
    ("Brave Girls", 1), ("HYOLYN", 1), ("Kep1er", 1), ("LOONA", 1), ("VIVIZ", 1), ("WJSN", 1),
], performer_rows
assert count_rows == [(6,)], count_rows

print("credited artists:", credited_rows)
print("performer tracks:", performer_rows)
print("album song count:", count_rows)
print("SQL OK")
```

- [ ] **Step 6: Run the SQL checker against the unmodified DAO**

```bash
python3 /tmp/ktool/check-album-artist-sql.py \
  /tmp/vivi-album-artist/app/src/main/kotlin/com/music/vivi/db/DatabaseDao.kt
```

Expected: `AssertionError: expected 1 credited-artists query, found 0`. This is the correct RED state - the queries do
not exist yet. Task 4 turns it green.

- [ ] **Step 7: No commit**

Task 1 changes no project file. `git -C /tmp/vivi-album-artist status --short` should still show only the patch-01
files.

---

### Task 2: The album-artist rule (pure unit)

**Files:**

- Create: `app/src/test/kotlin/com/music/vivi/playback/AlbumArtistTest.kt`
- Create: `app/src/main/kotlin/com/music/vivi/playback/AlbumArtist.kt`

- [ ] **Step 1: Write the failing test**

Create `app/src/test/kotlin/com/music/vivi/playback/AlbumArtistTest.kt`:

```kotlin
/**
 * vivimusic Project (C) 2026
 * Licensed under GPL-3.0 | See git history for contributors
 */

package com.music.vivi.playback

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class AlbumArtistTest {

    private fun performers(vararg tracks: Pair<String, Int>) =
        tracks.map { (artist, count) -> AlbumPerformerTracks(artist = artist, tracks = count) }

    @Test
    fun `a credit that performs nothing makes the album a compilation`() {
        val result = folderArtists(
            creditedArtists = listOf("Various Artists"),
            performerTracks = performers("HYOLYN" to 1, "WJSN" to 1, "Kep1er" to 1),
            albumSongCount = 6,
        )
        assertEquals(listOf("Various Artists"), result)
    }

    @Test
    fun `a localised credit becomes the fixed English folder name`() {
        val result = folderArtists(
            creditedArtists = listOf("Verschiedene Interpreten"),
            performerTracks = performers("HYOLYN" to 1, "WJSN" to 1, "Kep1er" to 1),
            albumSongCount = 6,
        )
        assertEquals(listOf(VARIOUS_ARTISTS), result)
    }

    @Test
    fun `credits that perform the album are used as the folder`() {
        val result = folderArtists(
            creditedArtists = listOf("Metallica"),
            performerTracks = performers("Metallica" to 10, "The Guest" to 1),
            albumSongCount = 11,
        )
        assertEquals(listOf("Metallica"), result)
    }

    @Test
    fun `a credit list keeps its order and drops duplicates and blanks`() {
        val result = folderArtists(
            creditedArtists = listOf("A", "B", "a", "  "),
            performerTracks = performers("A" to 5, "B" to 5),
            albumSongCount = 10,
        )
        assertEquals(listOf("A", "B"), result)
    }

    @Test
    fun `a split credit that someone performs is not a compilation`() {
        val result = folderArtists(
            creditedArtists = listOf("A", "B"),
            performerTracks = performers("A" to 5, "B" to 5),
            albumSongCount = 10,
        )
        assertEquals(listOf("A", "B"), result)
    }

    @Test
    fun `credits with no performer rows are still used as the folder`() {
        val result = folderArtists(
            creditedArtists = listOf("Metallica"),
            performerTracks = emptyList(),
            albumSongCount = 11,
        )
        assertEquals(listOf("Metallica"), result)
    }

    @Test
    fun `a credit that performs nothing wins even with a single performer`() {
        val result = folderArtists(
            creditedArtists = listOf("Hans Zimmer"),
            performerTracks = performers("Prague Philharmonic" to 12),
            albumSongCount = 12,
        )
        assertEquals(listOf(VARIOUS_ARTISTS), result)
    }

    @Test
    fun `six performers on six songs are a compilation`() {
        val result = folderArtists(
            creditedArtists = emptyList(),
            performerTracks = performers("A" to 1, "B" to 1, "C" to 1, "D" to 1, "E" to 1, "F" to 1),
            albumSongCount = 6,
        )
        assertEquals(listOf(VARIOUS_ARTISTS), result)
    }

    @Test
    fun `a guest on one track does not make a compilation`() {
        val result = folderArtists(
            creditedArtists = emptyList(),
            performerTracks = performers("Metallica" to 10, "The Guest" to 1),
            albumSongCount = 11,
        )
        assertNull(result)
    }

    @Test
    fun `a top performer on exactly half is not a compilation`() {
        val result = folderArtists(
            creditedArtists = emptyList(),
            performerTracks = performers("A" to 2, "B" to 2),
            albumSongCount = 4,
        )
        assertNull(result)
    }

    @Test
    fun `a single performer with no credit is not a compilation`() {
        val result = folderArtists(
            creditedArtists = emptyList(),
            performerTracks = performers("Metallica" to 5),
            albumSongCount = 5,
        )
        assertNull(result)
    }

    @Test
    fun `no credits and no performers means no folder artist`() {
        assertNull(folderArtists(emptyList(), emptyList(), 0))
    }

    @Test
    fun `duplicate performer rows are summed before the spread test`() {
        // Two rows for one artist, two tracks each. Summed, the top performer owns four of five songs
        // (4 * 2 < 5 is false, so it is not a compilation). Read one row at a time it would look like two
        // songs of five (2 * 2 < 5 is true) and the album would be mislabelled.
        val result = folderArtists(
            creditedArtists = emptyList(),
            performerTracks = performers("A" to 2, "A" to 2, "B" to 1),
            albumSongCount = 5,
        )
        assertNull(result)
    }

    @Test
    fun `names are compared trimmed and case-folded`() {
        val result = folderArtists(
            creditedArtists = listOf("  Metallica  "),
            performerTracks = performers("metallica" to 11),
            albumSongCount = 11,
        )
        assertEquals(listOf("Metallica"), result)
    }
}
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
/tmp/ktool/run-album-artist-tests.sh
```

Expected: FAIL - `kotlinc` reports `unresolved reference: folderArtists` and `unresolved reference:
AlbumPerformerTracks`, and the script exits non-zero before JUnit runs.

- [ ] **Step 3: Write the minimal implementation**

Create `app/src/main/kotlin/com/music/vivi/playback/AlbumArtist.kt`:

```kotlin
/**
 * vivimusic Project (C) 2026
 * Licensed under GPL-3.0 | See git history for contributors
 */

package com.music.vivi.playback

/**
 * The one folder name a compilation is filed under.
 *
 * Deliberately English and not localised, for the same reason as `Unknown Artist` in [DownloadFormat]: a
 * folder tree must not change when the user changes the app language.
 */
const val VARIOUS_ARTISTS = "Various Artists"

/**
 * One performer of an album and the number of that album's songs the performer is credited on.
 *
 * A Room projection of the grouped `song_artist_map` query in `DatabaseDao.albumPerformerTracks`: the
 * property names are the column names, so no Room import is needed and this file stays pure Kotlin.
 */
data class AlbumPerformerTracks(
    val artist: String,
    val tracks: Int,
)

/**
 * The artist a downloaded album is filed under, or null when the library knows nothing better than the
 * track's own artist.
 *
 * Two rules, in order:
 *
 * - **Credited mismatch**: the album has credited artists, at least one performer row exists, and no
 *   credited artist performs any of the album's songs. A compilation's album header credits an artist that
 *   is not on it - on YouTube Music the localised "Various Artists" pseudo-artist, elsewhere a composer or
 *   label credit - and that credit is not the folder its files belong under, so the fixed [VARIOUS_ARTISTS]
 *   name is used instead. Comparing names rather than looking for the pseudo-artist's missing channel link
 *   is what keeps this independent of the app language.
 * - **Performer spread**: with no credited artists stored at all, the album is a compilation when at least
 *   two performers share it and the most credited one owns under half of it (`top * 2 < albumSongCount`).
 *   The half rule keeps one guest verse from moving a whole album: 10 of 11 tracks is not a compilation,
 *   6 tracks by 6 artists is.
 *
 * @param creditedArtists the album's credited artists in display order, as stored in `album_artist_map`
 * @param performerTracks one row per artist credited on the album's songs, with that artist's song count
 * @param albumSongCount the number of the album's songs this library holds, the denominator of rule two
 */
internal fun folderArtists(
    creditedArtists: List<String>,
    performerTracks: List<AlbumPerformerTracks>,
    albumSongCount: Int,
): List<String>? {
    val credited = creditedArtists.namedDistinct()
    val performers = performerTracks.tracksByPerformer()
    val top = performers.values.maxOrNull() ?: 0
    return when {
        credited.isNotEmpty() && performers.isNotEmpty() && credited.none { it.normalised() in performers } ->
            listOf(VARIOUS_ARTISTS)
        credited.isNotEmpty() -> credited
        performers.size >= 2 && top * 2 < albumSongCount -> listOf(VARIOUS_ARTISTS)
        else -> null
    }
}

/** The stored spelling, in order, with blank names dropped and case-insensitive duplicates removed. */
private fun List<String>.namedDistinct(): List<String> =
    mapNotNull { name -> name.trim().takeIf { it.isNotEmpty() } }
        .distinctBy { it.normalised() }

/**
 * Song counts per performer, summed across the duplicate `artist` rows the schema can hold for one name.
 * An artist credited on none of the album's songs cannot skew the spread, so it is dropped.
 */
private fun List<AlbumPerformerTracks>.tracksByPerformer(): Map<String, Int> =
    groupBy { it.artist.normalised() }
        .mapValues { (_, rows) -> rows.sumOf { it.tracks } }
        .filterValues { it > 0 }

/** Trimmed and case-folded: the form every name comparison in this file uses. */
private fun String.normalised(): String = trim().lowercase()
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
/tmp/ktool/run-album-artist-tests.sh
```

Expected: `OK (<baseline> + 14 tests)`, then coverage lines for `DownloadFormat` and `AlbumArtistKt`. If
`AlbumArtistKt` shows uncovered lines, add a test - the 95% line gate covers this file.

- [ ] **Step 5: Commit in the scratch checkout**

```bash
cd /tmp/vivi-album-artist
git add app/src/main/kotlin/com/music/vivi/playback/AlbumArtist.kt \
        app/src/test/kotlin/com/music/vivi/playback/AlbumArtistTest.kt
git commit -m "the album-artist rule: credited mismatch, then performer spread"
```

---

### Task 3: `DownloadFormat` carries and uses the album artist

**Files:**

- Modify: `app/src/test/kotlin/com/music/vivi/playback/DownloadFormatTest.kt` (test helper and new cases)
- Modify: `app/src/main/kotlin/com/music/vivi/playback/DownloadFormat.kt`

- [ ] **Step 1: Extend the test helper and write the failing tests**

In `app/src/test/kotlin/com/music/vivi/playback/DownloadFormatTest.kt`, replace the private `input` helper so it takes
the new field. Find:

```kotlin
        bitrate: Int? = 256_000,
        trackNumber: Int? = null,
    ) = DownloadFormat.Input(
```

Replace with:

```kotlin
        bitrate: Int? = 256_000,
        trackNumber: Int? = null,
        folderArtists: List<String>? = null,
    ) = DownloadFormat.Input(
```

Then, in the same helper, find:

```kotlin
        bitrate = bitrate,
        trackNumber = trackNumber,
    )
```

Replace with:

```kotlin
        bitrate = bitrate,
        trackNumber = trackNumber,
        folderArtists = folderArtists,
    )
```

Now add these tests inside the `DownloadFormatTest` class body, after the last existing test but before the closing
brace:

```kotlin
    @Test
    fun `the folder template is filed under the album artist`() {
        val folders = DownloadFormat.expand(
            input(folderArtists = listOf("Various Artists")),
            "%artist%/%album%",
        )
        assertEquals(listOf("Various Artists", "Master Of Puppets"), folders)
    }

    @Test
    fun `the file name keeps the track artist when the folder uses the album artist`() {
        val compilation = input(artists = listOf("HYOLYN"), folderArtists = listOf("Various Artists"))
        assertEquals(
            "HYOLYN - Master Of Puppets - Enter Sandman",
            DownloadFormat.fileNameBase(compilation, "%artist% - %album% - %title%"),
        )
        assertEquals(
            listOf("Various Artists", "Master Of Puppets"),
            DownloadFormat.expand(compilation, "%artist%/%album%"),
        )
    }

    @Test
    fun `an absent, empty or blank album artist falls back to the track artist`() {
        val expected = listOf("Metallica", "Master Of Puppets")
        assertEquals(expected, DownloadFormat.expand(input(folderArtists = null), "%artist%/%album%"))
        assertEquals(expected, DownloadFormat.expand(input(folderArtists = emptyList()), "%artist%/%album%"))
        assertEquals(expected, DownloadFormat.expand(input(folderArtists = listOf("  ")), "%artist%/%album%"))
    }

    @Test
    fun `an album artist that sanitises away drops the segment like any other`() {
        assertEquals(
            emptyList<String>(),
            DownloadFormat.expand(input(folderArtists = listOf("..")), "%artist%"),
        )
    }

    @Test
    fun `the tidy pass applies to the album artist too`() {
        val cleaned = input(folderArtists = listOf("Various Artists", "Metallica - Topic")).cleaned()
        assertEquals(listOf("Various Artists", "Metallica"), cleaned.folderArtists)
    }

    @Test
    fun `an album artist cannot escape the root`() {
        assertEquals(
            listOf(".._.._etc"),
            DownloadFormat.expand(input(folderArtists = listOf("../../etc")), "%artist%"),
        )
    }

    @Test
    fun `usesArtistToken finds the token whatever its case`() {
        assertTrue(DownloadFormat.usesArtistToken("%artist%/%album%"))
        assertTrue(DownloadFormat.usesArtistToken("%Album%/%ARTIST%"))
        assertTrue(DownloadFormat.usesArtistToken("%artist%"))
        assertFalse(DownloadFormat.usesArtistToken("%album%/%year%"))
        assertFalse(DownloadFormat.usesArtistToken(""))
        assertFalse(DownloadFormat.usesArtistToken("plain folder"))
    }
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
/tmp/ktool/run-album-artist-tests.sh
```

Expected: FAIL - `kotlinc` reports `unresolved reference: folderArtists` (the `Input` constructor parameter) and
`unresolved reference: usesArtistToken`.

- [ ] **Step 3: Add the `folderArtists` field to `Input`**

In `app/src/main/kotlin/com/music/vivi/playback/DownloadFormat.kt`, find:

```kotlin
        /** Album position from `song_album_map`, 1-based. Null when the song has no album row. */
        val trackNumber: Int? = null,
    ) {
```

Replace with:

```kotlin
        /** Album position from `song_album_map`, 1-based. Null when the song has no album row. */
        val trackNumber: Int? = null,
        /**
         * The artists a *folder* is filed under: the album's credited artists, or `["Various Artists"]`
         * for a compilation. Null or blank falls back to [artists], which keeps an export working when the
         * library knows nothing about the album. The file-name template always uses [artists], so the
         * performer of each track stays visible in the file name.
         */
        val folderArtists: List<String>? = null,
    ) {
```

- [ ] **Step 4: Apply the tidy pass to the new field**

In the same file, find:

```kotlin
        fun cleaned(): Input = copy(
            title = title?.let(::tidyMetadata),
            artists = artists.map(::tidyArtist),
            albumTitle = albumTitle?.let(::tidyMetadata),
            storedAlbumName = storedAlbumName?.let(::tidyMetadata),
        )
```

Replace with:

```kotlin
        fun cleaned(): Input = copy(
            title = title?.let(::tidyMetadata),
            artists = artists.map(::tidyArtist),
            albumTitle = albumTitle?.let(::tidyMetadata),
            storedAlbumName = storedAlbumName?.let(::tidyMetadata),
            folderArtists = folderArtists?.map(::tidyArtist),
        )
```

- [ ] **Step 5: Resolve the folder's artist from the new field only**

In the same file, find the `resolve` function's artist branch:

```kotlin
    private fun resolve(token: String, literal: String, input: Input, forFileName: Boolean): String = when (token) {
        "artist" -> input.artists.joinToString(", ")
            .ifBlank { if (forFileName) "" else UNKNOWN_ARTIST }
```

Replace with:

```kotlin
    private fun resolve(token: String, literal: String, input: Input, forFileName: Boolean): String = when (token) {
        "artist" -> artistText(input, forFileName)
```

Then add these two private helpers. Find the doc comment that opens the next private helper:

```kotlin
    /**
     * The title never disappears from a file name; a folder segment is allowed to sanitise away.
```

Insert this text directly above it:

```kotlin
    /**
     * A folder is filed under the album's artist - the credited artists, or `Various Artists` for a
     * compilation - while a file name keeps the performer of that track, so the two templates disagree on
     * purpose. Everything else about the token, including the `Unknown Artist` placeholder, is unchanged.
     */
    private fun artistText(input: Input, forFileName: Boolean): String {
        val names = if (forFileName) input.artists else input.folderArtists.namedOrNull() ?: input.artists
        return names.joinToString(", ").ifBlank { if (forFileName) "" else UNKNOWN_ARTIST }
    }

    /** A list that is missing, empty or only blank names counts as absent. */
    private fun List<String>?.namedOrNull(): List<String>? =
        this?.filter { it.isNotBlank() }?.takeIf { it.isNotEmpty() }

```

- [ ] **Step 6: Add `usesArtistToken`**

In the same file, find:

```kotlin
    fun parse(template: String): ParseResult {
```

Insert directly above it:

```kotlin
    /**
     * Whether [template] uses the `%artist%` token, whatever its case. The exporter asks this before it
     * reads an album's artists, so a template that does not use the token costs no database reads.
     */
    internal fun usesArtistToken(template: String): Boolean =
        TOKEN_PATTERN.findAll(template).any { it.groupValues[1].equals("artist", ignoreCase = true) }

```

- [ ] **Step 7: Run the tests to verify they pass**

```bash
/tmp/ktool/run-album-artist-tests.sh
```

Expected: `OK (<baseline> + 21 tests)` and both `DownloadFormat` and `AlbumArtistKt` at full line
coverage.

- [ ] **Step 8: Commit in the scratch checkout**

```bash
cd /tmp/vivi-album-artist
git add app/src/main/kotlin/com/music/vivi/playback/DownloadFormat.kt \
        app/src/test/kotlin/com/music/vivi/playback/DownloadFormatTest.kt
git commit -m "the folder template resolves its artist from the album when it is known"
```

---

### Task 4: The three DAO queries

**Files:**

- Modify: `app/src/main/kotlin/com/music/vivi/db/DatabaseDao.kt`

- [ ] **Step 1: Add the import**

Find:

```kotlin
import com.music.vivi.models.toMediaMetadata
import com.music.vivi.ui.utils.resize
```

Replace with:

```kotlin
import com.music.vivi.models.toMediaMetadata
import com.music.vivi.playback.AlbumPerformerTracks
import com.music.vivi.ui.utils.resize
```

- [ ] **Step 2: Add the queries beside the existing hook**

Find the `albumIndex` hook that patch 01 already adds:

```kotlin
    /** The position of [songId] within [albumId] in `song_album_map` (0-based), or null when there is no row. */
    @Query("SELECT `index` FROM song_album_map WHERE songId = :songId AND albumId = :albumId LIMIT 1")
    suspend fun albumIndex(songId: String, albumId: String): Int?
```

Replace with the same lines plus the three new queries:

```kotlin
    /** The position of [songId] within [albumId] in `song_album_map` (0-based), or null when there is no row. */
    @Query("SELECT `index` FROM song_album_map WHERE songId = :songId AND albumId = :albumId LIMIT 1")
    suspend fun albumIndex(songId: String, albumId: String): Int?

    /**
     * The artists an album is credited to, in display order. Empty when the album header was never stored,
     * which is the case for a download taken straight from search or a playlist.
     */
    @Query(
        "SELECT artist.name FROM album_artist_map JOIN artist ON album_artist_map.artistId = artist.id " +
            "WHERE album_artist_map.albumId = :albumId ORDER BY album_artist_map.`order`",
    )
    suspend fun albumCreditedArtists(albumId: String): List<String>

    /**
     * How many of the album's songs each performer is credited on, most credited first. `DISTINCT songId`
     * because one song can carry several performers, and the count is what the performer-spread rule
     * compares against [albumSongCount].
     */
    @Query(
        "SELECT artist.name AS artist, COUNT(DISTINCT song_album_map.songId) AS tracks " +
            "FROM song_artist_map " +
            "JOIN song_album_map ON song_artist_map.songId = song_album_map.songId " +
            "JOIN artist ON song_artist_map.artistId = artist.id " +
            "WHERE song_album_map.albumId = :albumId GROUP BY artist.id ORDER BY tracks DESC",
    )
    suspend fun albumPerformerTracks(albumId: String): List<AlbumPerformerTracks>

    /** How many of the album's songs this library holds: the denominator of the performer-spread rule. */
    @Query("SELECT COUNT(DISTINCT songId) FROM song_album_map WHERE albumId = :albumId")
    suspend fun albumSongCount(albumId: String): Int
```

- [ ] **Step 3: Run the SQL dry-run to verify the queries are correct**

```bash
python3 /tmp/ktool/check-album-artist-sql.py \
  /tmp/vivi-album-artist/app/src/main/kotlin/com/music/vivi/db/DatabaseDao.kt
```

Expected output:

```text
credited artists: [('Various Artists',)]
performer tracks: [('WJSN', 1), ('HYOLYN', 1), ('Kep1er', 1), ('LOONA', 1), ('Brave Girls', 1), ('VIVIZ', 1)]
album song count: [(6,)]
SQL OK
```

The script extracts the SQL from the DAO, so it proves the DAO's own text runs - table names, column names, the
backticked `order` keyword and the grouping are all exercised. Room's own validation of the return type into
`AlbumPerformerTracks` happens in CI; if CI reports a Room error, the fix belongs on the projection's property names,
not on the SQL.

- [ ] **Step 4: Re-run the unit tests to prove nothing else changed**

```bash
/tmp/ktool/run-album-artist-tests.sh
```

Expected: `OK (<baseline> + 21 tests)`.

- [ ] **Step 5: Commit in the scratch checkout**

```bash
cd /tmp/vivi-album-artist
git add app/src/main/kotlin/com/music/vivi/db/DatabaseDao.kt
git commit -m "read the album's credited artists and performer spread"
```

---

### Task 5: Wire the exporter

**Files:**

- Modify: `app/src/main/kotlin/com/music/vivi/playback/DownloadFolderExporter.kt`

No local compile check is possible for this file (it imports Media3, Hilt and `android.net.Uri`). Match the snippets
exactly; CI compiles it.

- [ ] **Step 1: Read the album artist only when the template needs it**

Find in `exportLocked`:

```kotlin
            val cleanUp = context.dataStore[DownloadFormatCleanKey] != false
            val input = song.toTemplateInput(albumPosition(songId, song.album?.id))
                .let { if (cleanUp) it.cleaned() else it }
            val folderTemplate = DownloadFormat.templateOrDefault(context.dataStore[DownloadFolderTemplateKey])
            if (DownloadFormat.resolvedSegments(input, folderTemplate).size > DownloadFormat.MAX_SEGMENTS) {
```

Replace with:

```kotlin
            val cleanUp = context.dataStore[DownloadFormatCleanKey] != false
            // The template is read first so a folder format that does not use %artist% costs no album
            // lookups at all, the same way a disabled feature costs no database read.
            val folderTemplate = DownloadFormat.templateOrDefault(context.dataStore[DownloadFolderTemplateKey])
            val albumArtists = if (DownloadFormat.usesArtistToken(folderTemplate)) {
                albumFolderArtists(database, song.album?.id)
            } else {
                null
            }
            val input = song.toTemplateInput(albumPosition(songId, song.album?.id), albumArtists)
                .let { if (cleanUp) it.cleaned() else it }
            if (DownloadFormat.resolvedSegments(input, folderTemplate).size > DownloadFormat.MAX_SEGMENTS) {
```

- [ ] **Step 2: Pass the album artist through the metadata mapping**

Find the file-level extension at the end of the file:

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

Replace with:

```kotlin
/** Maps a library row onto the metadata the format can resolve. */
internal fun Song.toTemplateInput(
    trackNumber: Int? = null,
    folderArtists: List<String>? = null,
) = DownloadFormat.Input(
    songId = id,
    title = song.title,
    artists = artists.map { it.name },
    albumTitle = album?.title,
    storedAlbumName = song.albumName,
    songYear = song.year,
    albumYear = album?.year,
    bitrate = format?.bitrate,
    trackNumber = trackNumber,
    folderArtists = folderArtists,
)

/**
 * The artist an album's downloads are filed under, or null when the library knows nothing better than the
 * track's own artists.
 *
 * Best effort in the same shape as the exporter's own album-position lookup: an export is fired and
 * forgotten, so a failing lookup logs and returns null rather than failing the export or losing a
 * download. Shared with the settings preview, which is why it is not private.
 */
internal suspend fun albumFolderArtists(database: MusicDatabase, albumId: String?): List<String>? = try {
    albumId?.let { id ->
        folderArtists(
            creditedArtists = database.albumCreditedArtists(id),
            performerTracks = database.albumPerformerTracks(id),
            albumSongCount = database.albumSongCount(id),
        )
    }
} catch (e: CancellationException) {
    throw e
} catch (e: Exception) {
    Timber.tag(ALBUM_ARTIST_TAG).w(e, "Could not read the artists of album %s", albumId)
    null
}

/** Tag for the lookup above; the exporter class keeps its own TAG for the export path. */
private const val ALBUM_ARTIST_TAG = "AlbumArtist"
```

- [ ] **Step 3: Check every touched symbol exists and is spelled consistently**

```bash
cd /tmp/vivi-album-artist
grep -n "albumFolderArtists\|usesArtistToken\|folderArtists\|ALBUM_ARTIST_TAG" \
  app/src/main/kotlin/com/music/vivi/playback/DownloadFolderExporter.kt
grep -n "fun usesArtistToken" app/src/main/kotlin/com/music/vivi/playback/DownloadFormat.kt
grep -n "fun folderArtists\|const val VARIOUS_ARTISTS\|class AlbumPerformerTracks" \
  app/src/main/kotlin/com/music/vivi/playback/AlbumArtist.kt
```

Expected: `DownloadFolderExporter.kt` shows one `ALBUM_ARTIST_TAG` declaration, one `Timber.tag(ALBUM_ARTIST_TAG)`
use, the `albumFolderArtists` declaration, its call site inside the `usesArtistToken` branch, the `folderArtists`
parameter on `toTemplateInput`, and `folderArtists = folderArtists` in the `Input` construction. The other two greps
each match their one declaration. A typo here is the failure mode this step catches, because nothing else can compile
the file locally.

- [ ] **Step 4: Commit in the scratch checkout**

```bash
git add app/src/main/kotlin/com/music/vivi/playback/DownloadFolderExporter.kt
git commit -m "resolve the album artist for a folder template that uses %artist%"
```

---

### Task 6: Settings preview and the informational line

**Files:**

- Modify: `app/src/main/res/values/local_download_strings.xml`
- Modify: `app/src/main/kotlin/com/music/vivi/ui/screens/settings/LocalDownloadSettings.kt`

No local compile check is possible for the Kotlin file (Compose, Android). The XML is checked for well-formedness.

- [ ] **Step 1: Add the string**

In `app/src/main/res/values/local_download_strings.xml`, add this line directly after the
`download_folder_structure_hint` string, keeping the file's four-space indentation and its single blank line
before `</resources>`:

```xml
    <string name="download_folder_artist_note">%1$s is the album artist; compilations use Various Artists.</string>
```

- [ ] **Step 2: Check the XML is still well formed**

```bash
cd /tmp/vivi-album-artist
python3 -c "import xml.dom.minidom as m; m.parse('app/src/main/res/values/local_download_strings.xml')"
```

Expected: no output and exit code 0. A malformed document would raise instead.

- [ ] **Step 3: Import the shared lookup**

Find:

```kotlin
import com.music.vivi.playback.SafFolders
import com.music.vivi.playback.toTemplateInput
```

Replace with:

```kotlin
import com.music.vivi.playback.SafFolders
import com.music.vivi.playback.albumFolderArtists
import com.music.vivi.playback.toTemplateInput
```

- [ ] **Step 4: Resolve the album artist for the preview sample**

Find the state declarations:

```kotlin
    var sampleSong by remember { mutableStateOf<Song?>(null) }
    var sampleTrackNumber by remember { mutableStateOf<Int?>(null) }
```

Replace with:

```kotlin
    var sampleSong by remember { mutableStateOf<Song?>(null) }
    var sampleTrackNumber by remember { mutableStateOf<Int?>(null) }
    var sampleFolderArtists by remember { mutableStateOf<List<String>?>(null) }
```

Then find the whole preview-flavoured read:

```kotlin
    LaunchedEffect(Unit) {
        val sample: Pair<Song?, Int?> = try {
            withContext(Dispatchers.IO) {
                val found = database.downloadedSongsByCreateDateAsc().first().lastOrNull()
                found to found?.let { downloaded ->
                    downloaded.album?.id?.let { albumId ->
                        database.albumIndex(downloaded.id, albumId)?.plus(1)
                    }
                }
            }
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            Timber.tag(TAG).w(e, "Could not read a preview song, using the example")
            null to null
        }
        sampleSong = sample.first
        sampleTrackNumber = sample.second
    }
```

Replace with:

```kotlin
    LaunchedEffect(Unit) {
        var found: Song? = null
        var foundTrackNumber: Int? = null
        var foundFolderArtists: List<String>? = null
        try {
            withContext(Dispatchers.IO) {
                val song = database.downloadedSongsByCreateDateAsc().first().lastOrNull()
                found = song
                val albumId = song?.album?.id
                if (song != null && albumId != null) {
                    foundTrackNumber = database.albumIndex(song.id, albumId)?.plus(1)
                    // The preview must resolve the album artist the same way the exporter does, otherwise
                    // the dialog would promise a path the export does not write.
                    foundFolderArtists = albumFolderArtists(database, albumId)
                }
            }
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            Timber.tag(TAG).w(e, "Could not read a preview song, using the example")
            found = null
            foundTrackNumber = null
            foundFolderArtists = null
        }
        sampleSong = found
        sampleTrackNumber = foundTrackNumber
        sampleFolderArtists = foundFolderArtists
    }
```

- [ ] **Step 5: Pass it into the dialog**

Find:

```kotlin
            sampleSong = sampleSong,
            sampleTrackNumber = sampleTrackNumber,
```

Replace with:

```kotlin
            sampleSong = sampleSong,
            sampleTrackNumber = sampleTrackNumber,
            sampleFolderArtists = sampleFolderArtists,
```

- [ ] **Step 6: Accept and use it in the dialog**

Find:

```kotlin
    sampleSong: Song?,
    sampleTrackNumber: Int?,
    cleanUp: Boolean,
```

Replace with:

```kotlin
    sampleSong: Song?,
    sampleTrackNumber: Int?,
    sampleFolderArtists: List<String>?,
    cleanUp: Boolean,
```

Then find:

```kotlin
    val rawInput = sampleSong?.toTemplateInput(sampleTrackNumber) ?: example
```

Replace with:

```kotlin
    val rawInput = sampleSong?.toTemplateInput(sampleTrackNumber, sampleFolderArtists) ?: example
```

- [ ] **Step 7: Show the informational line for the folder field only**

Find, inside the dialog's preview `Column`:

```kotlin
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
```

Replace with:

```kotlin
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
            if (!editingFile) {
                Text(
                    text = stringResource(
                        R.string.download_folder_artist_note,
                        DownloadFormat.ARTIST_TOKEN,
                    ),
                    modifier = Modifier.padding(top = 8.dp),
                    style = MaterialTheme.typography.bodySmall,
                )
            }
```

- [ ] **Step 8: Check the wiring by grep**

```bash
cd /tmp/vivi-album-artist
grep -n "sampleFolderArtists" app/src/main/kotlin/com/music/vivi/ui/screens/settings/LocalDownloadSettings.kt
grep -n "download_folder_artist_note" \
  app/src/main/kotlin/com/music/vivi/ui/screens/settings/LocalDownloadSettings.kt \
  app/src/main/res/values/local_download_strings.xml
grep -c "albumFolderArtists" app/src/main/kotlin/com/music/vivi/ui/screens/settings/LocalDownloadSettings.kt
```

Expected: exactly five `sampleFolderArtists` lines - the state declaration, `sampleFolderArtists =
foundFolderArtists` inside `LaunchedEffect`, the `sampleFolderArtists = sampleFolderArtists` dialog
argument, the `sampleFolderArtists: List<String>?,` dialog parameter, and the use inside
`toTemplateInput(sampleTrackNumber, sampleFolderArtists)`. Then one `download_folder_artist_note`
line in each file, and `2` for the `albumFolderArtists` count (import plus call).

- [ ] **Step 9: Commit in the scratch checkout**

```bash
git add app/src/main/res/values/local_download_strings.xml \
        app/src/main/kotlin/com/music/vivi/ui/screens/settings/LocalDownloadSettings.kt
git commit -m "preview the album-artist folder and say what %artist% resolves to"
```

---

### Task 7: Extend the coverage gate to the new unit

**Files:**

- Modify: `app/build.gradle.kts`

- [ ] **Step 1: Add the new classes to the Kover scope**

Find the Kover block patch 01 adds:

```kotlin
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
```

Replace with:

```kotlin
        filters {
            includes {
                classes("com.music.vivi.playback.DownloadFormat*")
                classes("com.music.vivi.playback.AlbumArtist*")
            }
            excludes {
                // Each wildcard above also matches its own test class; test code is fully covered and must
                // not pad the number the gate measures.
                classes("com.music.vivi.playback.DownloadFormatTest")
                classes("com.music.vivi.playback.AlbumArtistTest")
            }
        }
```

`AlbumArtist*` matches `AlbumArtistKt`, the class the Kotlin compiler generates for a file's top-level declarations,
which is where `folderArtists` and `VARIOUS_ARTISTS` live. `AlbumPerformerTracks` is a data class in its own class
file, so it stays outside the gate - it holds no logic, only generated methods.

- [ ] **Step 2: Re-run the harness and read the coverage of the gated classes**

```bash
/tmp/ktool/run-album-artist-tests.sh
```

Expected: `OK (<baseline> + 21 tests)` plus two coverage lines, both fully covered. If `AlbumArtistKt` is under 100%,
add a test for the uncovered branch before continuing - CI's `koverVerify` fails the build below 95% lines.

- [ ] **Step 3: Commit in the scratch checkout**

```bash
cd /tmp/vivi-album-artist
git add app/build.gradle.kts
git commit -m "gate the album-artist rule at 95% line coverage too"
```

---

### Task 8: Regenerate the patch and commit it in the fork

**Files:**

- Modify: `local-patches/01-download-folder.patch` (in `/data/forks/vivi-music`)
- Modify: `local-patches/README.md` (in `/data/forks/vivi-music`)

- [ ] **Step 1: Generate the patch from the scratch checkout**

```bash
cd /tmp/vivi-album-artist
git add -A app/
git diff --cached main -- app/ > /tmp/album-artist-01.patch
wc -l /tmp/album-artist-01.patch local-patches/01-download-folder.patch
```

Expected: the new patch is longer than the old one. `git diff --cached main -- app/` is the command the spec's
Delivery section records: it stages the new files so they appear as `new file mode`, and it scopes the diff to `app/`
so no document or process note can leak into upstream's tree.

- [ ] **Step 2: Check the patch touches exactly the expected files**

```bash
grep '^diff --git' /tmp/album-artist-01.patch
grep -c '^diff --git' /tmp/album-artist-01.patch
grep -n 'docs/agent\|TODO\|TBD' /tmp/album-artist-01.patch || echo "no stray paths or placeholders"
```

Expected: 13 `diff --git` lines -

```text
a/app/build.gradle.kts
a/app/src/main/kotlin/com/music/vivi/db/DatabaseDao.kt
a/app/src/main/kotlin/com/music/vivi/playback/AlbumArtist.kt            (new file)
a/app/src/main/kotlin/com/music/vivi/playback/DownloadFolderExporter.kt
a/app/src/main/kotlin/com/music/vivi/playback/DownloadFormat.kt
a/app/src/main/kotlin/com/music/vivi/playback/DownloadUtil.kt
a/app/src/main/kotlin/com/music/vivi/playback/LocalDownloadPrefs.kt
a/app/src/main/kotlin/com/music/vivi/playback/SafFolders.kt
a/app/src/main/kotlin/com/music/vivi/ui/screens/settings/LocalDownloadSettings.kt
a/app/src/main/kotlin/com/music/vivi/ui/screens/settings/StorageSettings.kt
a/app/src/main/res/values/local_download_strings.xml
a/app/src/test/kotlin/com/music/vivi/playback/AlbumArtistTest.kt        (new file)
a/app/src/test/kotlin/com/music/vivi/playback/DownloadFormatTest.kt
```

and `no stray paths or placeholders`.

- [ ] **Step 3: Install the patch and prove it still applies to pristine main**

```bash
cd /data/forks/vivi-music
git status --short          # must show only '?? docs/agent/...' entries, no modified app/ files
cp /tmp/album-artist-01.patch local-patches/01-download-folder.patch
./local-patches/apply.sh --check
```

Expected: `OK   01-download-folder.patch (applies)` and a clean status for `app/`. If the status shows an edited
`app/` file, stop: the fork's tree was modified by mistake and must be restored with `git checkout -- app/` before
continuing.

- [ ] **Step 4: End-to-end proof on a fresh checkout of the new patch**

```bash
rm -rf /tmp/vivi-album-artist-verify
git clone --no-hardlinks /data/forks/vivi-music /tmp/vivi-album-artist-verify
cd /tmp/vivi-album-artist-verify && ./local-patches/apply.sh
/tmp/ktool/run-album-artist-tests.sh /tmp/vivi-album-artist-verify
python3 /tmp/ktool/check-album-artist-sql.py \
  /tmp/vivi-album-artist-verify/app/src/main/kotlin/com/music/vivi/db/DatabaseDao.kt
```

Expected: the patch applies, `OK (<baseline> + 21 tests)`, full coverage on both gated classes, and
`SQL OK`. This proves the committed patch is complete on its own - a fresh upstream tree plus the patch
reproduces everything.

- [ ] **Step 5: Update `local-patches/README.md`**

In the "What patch 01 does" section, find the folder-structure bullet's final clause:

```markdown
  `%artist%`, `%album%`, `%year%`, `%title%`, `%songId%`, `%quality%` and `%tracknumber%` are supported,
  an unresolvable token becomes `Unknown Artist` / `Unknown Album` / `Unknown Year` / `Unknown Quality`,
  and an explicitly emptied template means flat output directly in the root.
```

Replace with:

```markdown
  `%artist%`, `%album%`, `%year%`, `%title%`, `%songId%`, `%quality%` and `%tracknumber%` are supported,
  an unresolvable token becomes `Unknown Artist` / `Unknown Album` / `Unknown Year` / `Unknown Quality`,
  and an explicitly emptied template means flat output directly in the root. In a *folder* format
  `%artist%` is the artist the album is filed under - the credited album artist when the library knows it,
  or the fixed `Various Artists` for a compilation, defined as an album whose credit performs none of its
  tracks, or (with no credit stored) one shared by at least two performers where no performer owns half of
  it. The *file-name* format keeps using the track's own artist, so a compilation's folder is uniform while
  each file name still names its performer.
```

Then, in the "Known limitations" table, add two rows after the existing "A directory carries the export's name" row:

```markdown
| A credit that performs nothing becomes `Various Artists` | An album credited to a composer, a label or a compilation pseudo-artist rather than to its performers is filed under `Various Artists`. That credit is deliberately discarded: it is not a name the album's files belong under, and matching the localised text of the pseudo-artist instead would make the folder tree depend on the app language. |
| A two-track release by two artists is not detected | The performer-spread rule needs the top performer to own *under* half of the album, and on a two-track release one performer owns exactly half, so such an album is filed under its first track's artist. The credited-artist rule still catches it whenever the album header was stored. |
```

- [ ] **Step 6: Commit in the fork repository**

```bash
cd /data/forks/vivi-music
markdownlint --fix local-patches/README.md || true
git add local-patches/01-download-folder.patch local-patches/README.md
git commit -m "local: file the folder artist under the album artist for compilations"
git log --oneline -3
git status --short
```

Expected: one commit with two files changed, and a status listing only the untracked `docs/agent/` entries
(`markdownlint` has no config in this repository, so it reports the 80-character `MD013` default; the repository
standard is 120 with no limit in tables, and no other rule may be reported). Do not commit anything under `docs/` in
this task.

---

### Task 9: Acceptance walk-through and hand-off

**Files:** none - this task produces the report the next chain step consumes.

- [ ] **Step 1: Re-run every local gate from the committed patch**

```bash
cd /data/forks/vivi-music
./local-patches/apply.sh --check
rm -rf /tmp/vivi-album-artist-final
git clone --no-hardlinks /data/forks/vivi-music /tmp/vivi-album-artist-final
cd /tmp/vivi-album-artist-final && ./local-patches/apply.sh
/tmp/ktool/run-album-artist-tests.sh /tmp/vivi-album-artist-final
python3 /tmp/ktool/check-album-artist-sql.py \
  /tmp/vivi-album-artist-final/app/src/main/kotlin/com/music/vivi/db/DatabaseDao.kt
cd /tmp/vivi-album-artist-final
python3 -c "import xml.dom.minidom as m; m.parse('app/src/main/res/values/local_download_strings.xml')"
```

Expected: patch applies, `OK (<baseline> + 21 tests)`, full coverage on `DownloadFormat` and `AlbumArtistKt`, `SQL
OK`, and the XML check exiting 0. Paste the real output into the report; do not summarise it from memory.

- [ ] **Step 2: Record the criteria that only CI can decide**

State these in the report as unverified-locally, with the CI job that will decide them:

| Item | Decided by |
| --- | --- |
| `DatabaseDao.kt`, `DownloadFolderExporter.kt` and `LocalDownloadSettings.kt` compile | `assembleUniversalFossDebug` |
| The three queries are valid for Room and `albumPerformerTracks` maps into `AlbumPerformerTracks` | `assembleUniversalFossDebug` (Room's compile-time validation) |
| The 95% Kover line gate over `DownloadFormat*` and `AlbumArtist*` | `koverVerify` |
| No new Compose or resource mistakes | `lintUniversalFossDebug` (report only) |
| The patch applies to pristine upstream, not just to this fork | `Upstream Drift Check`, and `Local Patch Build` on push |

- [ ] **Step 3: List what a reviewer must read by hand**

The three changed upstream bodies are small and are the only code no local check compiles: `exportLocked`'s new four
lines in `DownloadFolderExporter.kt`, the `albumFolderArtists` helper, `toTemplateInput`'s new parameter, and
`DownloadLocalSettings.kt`'s preview read. Everything else is covered by the harness.

---

## Spec coverage

| Spec requirement | Task |
| --- | --- |
| Folder `%artist%` resolution order: compilation, credited artist, track artist, `Unknown Artist` | Tasks 2, 3, 5 |
| File-name `%artist%` unchanged | Task 3 (test `the file name keeps the track artist when the folder uses the album artist`) |
| Rule A: credits present, at least one performer row, no credited artist performs a track | Task 2 (tests 1, 2, 6, 7, 14) |
| Rule B: no credits, at least two performers, top performer under half | Task 2 (tests 8, 9, 10, 11, 12, 13) |
| Vacuous case: credits but no performer rows is not a compilation | Task 2 (test 6) |
| Names compared trimmed and case-folded | Task 2 (test 14) |
| Credited names joined with `", "`, in order, de-duplicated | Task 2 (tests 4, 5), Task 3 (`expand` through the existing join) |
| Fixed, non-localised `Various Artists` | Task 2 (tests 1, 2) |
| New pure `playback/AlbumArtist.kt` with the `AlbumPerformerTracks` projection | Task 2 |
| `Input.folderArtists`, tidy pass, `usesArtistToken` | Task 3 |
| Three DAO queries | Task 4 |
| Reads only when the template uses `%artist%`, best-effort with logs | Task 5 |
| Settings preview agrees with the exporter plus one informational line | Tasks 6 |
| Kover scope extended to `AlbumArtist*` | Task 7 |
| Patch regeneration, `README.md` update, `app/`-only diff | Task 8 |
| Documentation of the two consequences as known limitations | Task 8 (Step 5) |
| Acceptance criteria 1-6 of the spec | Tasks 2-4 locally, Task 8 Step 4 end to end, Task 9 for the CI-decided remainder |

No spec requirement is left without a task. The spec's out-of-scope list is respected: `%album%` is untouched, no
preference was added, no schema change, no `%albumartist%` token, and files already written are never moved.

## Self-review notes

- Placeholder scan: every code step in this plan contains the complete replacement text; no step says "add validation"
  or "similar to Task N".
- Type consistency: `folderArtists(creditedArtists, performerTracks, albumSongCount)` (Task 2) is called with those
  exact named arguments in Task 5; `AlbumPerformerTracks(artist, tracks)` is used identically in Tasks 2 and 4;
  `Input.folderArtists` is the one field name used in Tasks 3, 5 and 6; `usesArtistToken` is spelled the same in Tasks
  3 and 5; `albumFolderArtists(database, albumId)` has one declaration (Task 5) and two call sites (Tasks 5 and 6).
- Test count: the plan adds 14 tests to `AlbumArtistTest` and 7 to `DownloadFormatTest`, so the harness output after
  Task 3 is the Task 1 baseline plus 21. If a count differs, read the failure output rather than adjusting an
  assertion.
- One deliberate deviation to watch: `LocalDownloadSettings.kt` gains an `albumFolderArtists` import between
  `SafFolders` and `toTemplateInput`, which is the ASCII order this codebase's import blocks use (upper case before
  lower case).
