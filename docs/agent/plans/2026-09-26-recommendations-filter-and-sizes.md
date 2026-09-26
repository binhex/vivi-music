# Recommendation Filter and Section Sizes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use sub-agents (recommended) to implement this plan task-by-task. Steps
use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the home-screen sections Quick Picks, Daily Discover and Covers & Remixes suggest music related to the
user's downloads, never repeat anything already downloaded, and read their item counts from three configurable settings
defaulting to 50.

**Architecture:** All logic lives in fork-owned files. A pure Kotlin object (`RecommendationFilter`) holds every rule -
exclusion, the collection rule, size clamping, seed selection and padding - and is unit-tested on the JVM. Upstream
`HomeViewModel` receives the Media3 download state once per refresh and makes short calls into that object; upstream
`ContentSettings` gains one line that renders the fork-owned settings group.

**Tech Stack:** Kotlin, Jetpack Compose (Material 3), Hilt, Room, Media3 ExoPlayer offline downloads, DataStore
Preferences, JUnit 4. Delivery is a single patch file, `local-patches/02-recommendations.patch`.

Spec: `docs/agent/specs/2026-09-26-recommendation-filter-and-section-size-design.md` (approved, commit `aff13f6f`).

---

## Scope

One subsystem: the recommendation rows on the home screen. No split into separate plans is needed - the
work produces one patch, one set of settings and one test file.

## How work lands in this fork (read this first)

This fork **never commits an upstream file**. Every change, including new Kotlin files, is recorded
inside a patch file and applied to a fresh upstream checkout at build time. The rules below follow what
patch 01 (`01-download-folder.patch`) already does.

1. Work in a scratch tree: a fresh clone of upstream `main` with patch 01 applied.
2. Create and edit files there. New fork-owned files are created in the scratch tree, never in the fork.
3. Run the pure unit tests locally with the standalone Kotlin harness (this machine has JDK 11 only and
   no Android SDK, so Gradle cannot compile the app here).
4. Regenerate `local-patches/02-recommendations.patch` from a base tree that has upstream + patch 01.
5. Verify the patch applies cleanly on a fresh upstream clone, that it touches only the intended files,
   and that it does not alter patch 01's own lines except the two Kover lines named in Task 14.
6. Commit only fork-owned files: the patch and `local-patches/README.md`.
7. CI (`Local Patch Build`) is the authoritative compiler and gate. Local `gradle`/`lint`/`kover` runs
   are impossible on this machine - do not attempt them and do not claim they passed.

Local test harness (already present on this machine, verified working):

```text
/tmp/ktool/kotlinc2310/kotlinc/bin/kotlinc   standalone Kotlin 2.3.10 compiler
/tmp/ktool/junit.jar  /tmp/ktool/hamcrest.jar  JUnit 4 runner + matcher
/tmp/ktool/jacoco-agent.jar /tmp/ktool/jacoco-cli.jar  line-coverage measurement
/tmp/ktool/run-album-artist-tests.sh   the shape to copy for a new runner
```

## Upstream drift found during implementation (2026-09-26)

The scratch tree is a fresh clone of current upstream `main`, which is newer than this fork's own snapshot.
Three plan statements are superseded by what the code actually looks like. Where a task below conflicts with
this section, this section wins; the intent of every task is unchanged.

1. **`getQuickPicks()` no longer exists.** Upstream split it into `getQuickPicksLocal()` and
   `enrichQuickPicksFromNetwork()` (launched from `loadNetworkDataPhase`). Task 9 therefore applies the
   filtering and `quickPicksSize` in `getQuickPicksLocal` (related songs, forgotten favourites, every
   fallback tier, the `ifEmpty` fallback and the `LAST_LISTEN` branch) and puts the downloaded-seed block in
   `enrichQuickPicksFromNetwork`, after the existing `YouTube.related(...)` call and after the
   `endpoint == null` early return so the lookups stay bounded. Upstream's new `QP_TIMING` logs and the new
   phase-2 job wiring are left as they are.
2. **`keepSuggestible` needs two shapes, not one.** The Room entity `Album` extends the sealed `LocalItem`,
   not `YTItem`, so a `List<YTItem>` helper cannot accept `mostPlayedAlbums()`, and `item is Album` on a
   `YTItem` is an impossible check. Task 8 therefore provides `keepSuggestible(items: List<YTItem>)` for
   innertube items (Similar Recommendations, using `albumSongs(browseId)` for innertube albums) and
   `keepSuggestibleAlbums(items: List<Album>)` for the Keep Listening database row, which keeps the existing
   `it.album.thumbnailUrl` filter instead of a cast.
3. **`loadMoreYouTubeItems` also writes the Covers & Remixes row.** It is not named in Task 11, but it
   appends to the same row, so the same `keepUndownloaded` filter is applied there too; otherwise the
   "load more" path could reintroduce downloaded items into a row the spec says must not show them.

## File map

**Created inside the patch (fork-owned):**

| Path | Responsibility |
| --- | --- |
| `app/src/main/kotlin/com/music/vivi/playback/RecommendationFilter.kt` | Pure rules: clamp, completed-id set, exclusion, collection rule, seeds, padding |
| `app/src/main/kotlin/com/music/vivi/playback/DownloadedIds.kt` | Pure mapper from Media3's id to state map into filter snapshots |
| `app/src/main/kotlin/com/music/vivi/playback/LocalRecommendationPrefs.kt` | Three DataStore int keys |
| `app/src/main/kotlin/com/music/vivi/ui/screens/settings/LocalRecommendationSettings.kt` | Settings group: three rows opening a number dialog |
| `app/src/main/res/values/local_recommendation_strings.xml` | Strings for that group |
| `app/src/test/kotlin/com/music/vivi/playback/RecommendationFilterTest.kt` | JUnit tests for the pure rules |
| `app/src/test/kotlin/com/music/vivi/playback/DownloadedIdsTest.kt` | JUnit tests for the mapper |

**Modified inside the patch (upstream files, hooks only):**

| Path | Change |
| --- | --- |
| `app/src/main/kotlin/com/music/vivi/viewmodels/HomeViewModel.kt` | Inject `DownloadUtil`; read sizes and download states; filter six rows; add downloaded seeds; pad the covers row; use configured sizes |
| `app/src/main/kotlin/com/music/vivi/ui/screens/settings/ContentSettings.kt` | One line calling `LocalRecommendationSettingsGroup()` |
| `app/src/main/kotlin/com/music/vivi/playback/DownloadRecovery.kt` | One line: promote the private Media3 completed-state constant so the filter can alias it instead of duplicating it |
| `app/build.gradle.kts` | Four lines inside patch 01's `kover { }` block, adding the new classes to the coverage allowlist |

**Fork-owned files committed by this plan:**

| Path | Change |
| --- | --- |
| `local-patches/02-recommendations.patch` | New file: the whole feature |
| `local-patches/README.md` | New section describing patch 02 |

---

### Task 1: Scratch tree and local test harness

**Files:**

- Create: `/tmp/vivi-reco` (clone), `/tmp/ktool/run-recommendation-filter-tests.sh`

- [ ] **Step 1: Clone upstream and apply patch 01**

```bash
rm -rf /tmp/vivi-reco
git clone --depth 1 --quiet https://github.com/vivizzz007/vivi-music /tmp/vivi-reco
cd /tmp/vivi-reco
/data/forks/vivi-music/local-patches/apply.sh
```

Expected: `OK   01-download-folder.patch (applied)` then
`OK   pinned debug keystore installed as app/persistent-debug.keystore`.

- [ ] **Step 2: Snapshot the base so patch 02 can be generated as a diff against it**

```bash
cd /tmp/vivi-reco
git add -A
git -c user.email=patch@local -c user.name=patch commit -qm "base: upstream + patch 01"
git log --oneline -1
```

Expected: one commit hash and the subject `base: upstream + patch 01`.

- [ ] **Step 3: Write the local test runner**

Create `/tmp/ktool/run-recommendation-filter-tests.sh`:

```bash
#!/usr/bin/env bash
# Compiles the pure recommendation-filter units and their tests with a standalone Kotlin compiler, then
# runs JUnit directly. This machine has JDK 11 and no Android SDK, so Gradle cannot run here; CI is the
# authoritative gate. Usage: run-recommendation-filter-tests.sh [repo-root]
set -euo pipefail

REPO="${1:-/tmp/vivi-reco}"
TOOL=/tmp/ktool
MAIN="$REPO/app/src/main/kotlin/com/music/vivi/playback"
TEST="$REPO/app/src/test/kotlin/com/music/vivi/playback"
OUT="$TOOL/recommendation-filter-out"
STDLIB="$TOOL/kotlinc2310/kotlinc/lib/kotlin-stdlib.jar"
CP="$TOOL/junit.jar:$TOOL/hamcrest.jar"

rm -rf "$OUT" && mkdir -p "$OUT"

"$TOOL/kotlinc2310/kotlinc/bin/kotlinc" -nowarn -cp "$CP" -d "$OUT" \
  "$MAIN/RecommendationFilter.kt" \
  "$MAIN/DownloadedIds.kt" \
  "$TEST/RecommendationFilterTest.kt" \
  "$TEST/DownloadedIdsTest.kt"

java -javaagent:"$TOOL/jacoco-agent.jar=destfile=$OUT/jacoco.exec" \
  -cp "$OUT:$CP:$STDLIB" \
  org.junit.runner.JUnitCore \
  com.music.vivi.playback.RecommendationFilterTest \
  com.music.vivi.playback.DownloadedIdsTest

java -jar "$TOOL/jacoco-cli.jar" report "$OUT/jacoco.exec" \
  --classfiles "$OUT" --sourcefiles "$MAIN" --csv "$OUT/jacoco.csv" --quiet

awk -F, 'NR == 1 || $3 ~ /^RecommendationFilter/ || $3 == "DownloadedIds" {
  printf "%-24s line coverage %s/%s\n", $3, $9, $8 + $9
}' "$OUT/jacoco.csv"
```

- [ ] **Step 4: Prove the harness works before writing any new code**

```bash
chmod +x /tmp/ktool/run-recommendation-filter-tests.sh
bash /tmp/ktool/run-album-artist-tests.sh /tmp/vivi-reco
```

Expected: `OK (n tests)` from JUnitCore and coverage lines for `AlbumArtistKt`, `DownloadFormat`,
`DownloadStallPolicy`, `DownloadRecoveryKt`. If this fails, stop and fix the environment before continuing.

- [ ] **Step 5: Commit the scratch state**

```bash
cd /tmp/vivi-reco && git add -A && git -c user.email=patch@local -c user.name=patch commit -qm "harness ready"
```

---

### Task 2: Filter core - clamping, exclusion and resizing

**Files:**

- Create: `/tmp/vivi-reco/app/src/main/kotlin/com/music/vivi/playback/RecommendationFilter.kt`
- Test: `/tmp/vivi-reco/app/src/test/kotlin/com/music/vivi/playback/RecommendationFilterTest.kt`

- [ ] **Step 1: Write the failing tests**

Create `RecommendationFilterTest.kt`:

```kotlin
/**
 * vivimusic Project (C) 2026
 * Licensed under GPL-3.0 | See git history for contributors
 */

package com.music.vivi.playback

import org.junit.Assert.assertEquals
import org.junit.Test

class RecommendationFilterTest {

    @Test
    fun `clampSize keeps values inside the supported range`() {
        assertEquals(10, RecommendationFilter.clampSize(0))
        assertEquals(10, RecommendationFilter.clampSize(10))
        assertEquals(50, RecommendationFilter.clampSize(50))
        assertEquals(200, RecommendationFilter.clampSize(200))
        assertEquals(200, RecommendationFilter.clampSize(9_999))
    }

    @Test
    fun `keepUndownloaded drops downloaded ids and keeps the order`() {
        val items = listOf("a", "b", "c", "d")

        val kept = RecommendationFilter.keepUndownloaded(items, setOf("b", "d")) { it }

        assertEquals(listOf("a", "c"), kept)
    }

    @Test
    fun `keepUndownloaded with no downloads keeps everything`() {
        val items = listOf("a", "b")

        val kept = RecommendationFilter.keepUndownloaded(items, emptySet()) { it }

        assertEquals(items, kept)
    }

    @Test
    fun `resize takes at most the clamped size`() {
        val items = (1..300).map { it.toString() }

        assertEquals(200, RecommendationFilter.resize(items, 999).size)
        assertEquals(50, RecommendationFilter.resize(items, 50).size)
        assertEquals(10, RecommendationFilter.resize((1..20).map { it.toString() }, 1).size)
    }

    @Test
    fun `resize never invents items`() {
        assertEquals(1, RecommendationFilter.resize(listOf("a"), 1).size)
    }
}
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
bash /tmp/ktool/run-recommendation-filter-tests.sh /tmp/vivi-reco
```

Expected: compilation failure, `unresolved reference: RecommendationFilter`. The runner cannot even load the class
because it does not exist yet.

- [ ] **Step 3: Write the minimal implementation**

Create `RecommendationFilter.kt`:

```kotlin
/**
 * vivimusic Project (C) 2026
 * Licensed under GPL-3.0 | See git history for contributors
 */

package com.music.vivi.playback

/**
 * Pure rules behind the "hide what I already downloaded, show more per section" patch.
 *
 * Nothing here touches Android, Media3 or Compose on purpose: this is the part of the feature that runs
 * on any JVM, so it is fully unit-tested and measured by CI's Kover gate. The one Android touch - reading
 * Media3's download state - happens in HomeViewModel and is mapped into [DownloadSnapshot] by
 * [DownloadedIds].
 */
object RecommendationFilter {
    /** Smallest and largest number of items a section may be configured to show. */
    const val MIN_SECTION_SIZE = 10
    const val MAX_SECTION_SIZE = 200

    /** Item count every configurable section uses until the user changes it. */
    const val DEFAULT_SECTION_SIZE = 50

    /** How many downloaded songs may be added on top of the existing seeds. */
    const val MAX_DOWNLOAD_SEEDS = 5

    /** Media3's Download.STATE_COMPLETED, repeated so this file needs no Media3 dependency. */
    const val STATE_COMPLETED = 3

    /** One download as the adapter sees it: the item id and Media3's state code. */
    data class DownloadSnapshot(val id: String, val state: Int)

    /** Clamp a configured section size into the supported range. */
    fun clampSize(value: Int): Int = value.coerceIn(MIN_SECTION_SIZE, MAX_SECTION_SIZE)

    /** Drop items whose id is already downloaded, keeping the original order. */
    fun <T> keepUndownloaded(items: List<T>, downloadedIds: Set<String>, idOf: (T) -> String): List<T> =
        items.filterNot { idOf(it) in downloadedIds }

    /** Take at most the clamped `size` items, keeping the original order. */
    fun <T> resize(items: List<T>, size: Int): List<T> = items.take(clampSize(size))
}
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
bash /tmp/ktool/run-recommendation-filter-tests.sh /tmp/vivi-reco
```

Expected: `OK (5 tests)` and coverage lines for `RecommendationFilter` showing zero missed lines.

- [ ] **Step 5: Commit**

```bash
cd /tmp/vivi-reco
git add -A
git -c user.email=patch@local -c user.name=patch commit -qm "feat: pure recommendation filter core"
```

---

### Task 3: Completed-id set and the collection rule

**Files:**

- Modify: `/tmp/vivi-reco/app/src/main/kotlin/com/music/vivi/playback/RecommendationFilter.kt`
- Test: `/tmp/vivi-reco/app/src/test/kotlin/com/music/vivi/playback/RecommendationFilterTest.kt`

- [ ] **Step 1: Write the failing tests**

Append to `RecommendationFilterTest.kt` (inside the class):

```kotlin
    @Test
    fun `completedIds keeps only finished downloads`() {
        val snapshots = listOf(
            RecommendationFilter.DownloadSnapshot("finished", RecommendationFilter.STATE_COMPLETED),
            RecommendationFilter.DownloadSnapshot("queued", 0),
            RecommendationFilter.DownloadSnapshot("downloading", 2),
            RecommendationFilter.DownloadSnapshot("failed", 1),
        )

        assertEquals(setOf("finished"), RecommendationFilter.completedIds(snapshots))
    }

    @Test
    fun `keepCollection keeps a collection whose tracks are not all downloaded`() {
        val downloaded = setOf("t1", "t2")

        assertEquals(true, RecommendationFilter.keepCollection(listOf("t1", "t2", "t3"), downloaded))
        assertEquals(true, RecommendationFilter.keepCollection(listOf("t3"), downloaded))
    }

    @Test
    fun `keepCollection hides only a fully downloaded collection`() {
        val downloaded = setOf("t1", "t2")

        assertEquals(false, RecommendationFilter.keepCollection(listOf("t1", "t2"), downloaded))
    }

    @Test
    fun `keepCollection keeps a collection whose membership is unknown`() {
        assertEquals(true, RecommendationFilter.keepCollection(emptyList(), setOf("t1")))
    }
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
bash /tmp/ktool/run-recommendation-filter-tests.sh /tmp/vivi-reco
```

Expected: compilation failure, `unresolved reference: completedIds` and `unresolved reference: keepCollection`.

- [ ] **Step 3: Write the minimal implementation**

Add to `RecommendationFilter` (after `clampSize`):

```kotlin
    /** Ids of downloads that finished. Queued, running and failed downloads are not "downloaded". */
    fun completedIds(snapshots: List<DownloadSnapshot>): Set<String> =
        snapshots.filter { it.state == STATE_COMPLETED }.map { it.id }.toSet()

    /**
     * Whether a collection (album or playlist) may still be suggested.
     *
     * A collection is hidden only when it has tracks and every one of them is downloaded. An empty track
     * list means membership could not be determined, so the collection is kept rather than hidden.
     */
    fun keepCollection(trackIds: List<String>, downloadedIds: Set<String>): Boolean =
        trackIds.isEmpty() || trackIds.any { it !in downloadedIds }
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
bash /tmp/ktool/run-recommendation-filter-tests.sh /tmp/vivi-reco
```

Expected: `OK (9 tests)`.

- [ ] **Step 5: Commit**

```bash
cd /tmp/vivi-reco
git add -A
git -c user.email=patch@local -c user.name=patch commit -qm "feat: completed-download ids and collection rule"
```

---

### Task 4: Seeds and padding

**Files:**

- Modify: `/tmp/vivi-reco/app/src/main/kotlin/com/music/vivi/playback/RecommendationFilter.kt`
- Test: `/tmp/vivi-reco/app/src/test/kotlin/com/music/vivi/playback/RecommendationFilterTest.kt`

- [ ] **Step 1: Write the failing tests**

Append to `RecommendationFilterTest.kt`:

```kotlin
    @Test
    fun `seedIds appends downloaded songs that are not already seeds`() {
        val seeds = RecommendationFilter.seedIds(
            playedSeeds = listOf("played1", "played2"),
            downloadedSongs = listOf("played2", "down1", "down2"),
            maxDownloaded = RecommendationFilter.MAX_DOWNLOAD_SEEDS,
        )

        assertEquals(listOf("played1", "played2", "down1", "down2"), seeds)
    }

    @Test
    fun `seedIds caps the downloaded additions`() {
        val seeds = RecommendationFilter.seedIds(
            playedSeeds = listOf("played1"),
            downloadedSongs = listOf("d1", "d2", "d3", "d4", "d5", "d6", "d7"),
            maxDownloaded = RecommendationFilter.MAX_DOWNLOAD_SEEDS,
        )

        assertEquals(listOf("played1", "d1", "d2", "d3", "d4", "d5"), seeds)
    }

    @Test
    fun `seedIds returns the played seeds unchanged when nothing is downloaded`() {
        val seeds = RecommendationFilter.seedIds(listOf("a", "b"), emptyList(), RecommendationFilter.MAX_DOWNLOAD_SEEDS)

        assertEquals(listOf("a", "b"), seeds)
    }

    @Test
    fun `pad prefers remote items, then local ones, without duplicates`() {
        val padded = RecommendationFilter.pad(
            remote = listOf("r1", "r2", "shared"),
            local = listOf("l1", "shared", "l2"),
            size = 10,
            downloadedIds = emptySet(),
            idOf = { it },
        )

        assertEquals(listOf("r1", "r2", "shared", "l1", "l2"), padded)
    }

    @Test
    fun `pad caps the row at the configured size`() {
        val remote = (1..12).map { "r$it" }

        val padded = RecommendationFilter.pad(
            remote = remote,
            local = emptyList(),
            size = 10,
            downloadedIds = emptySet(),
            idOf = { it },
        )

        assertEquals(10, padded.size)
        assertEquals(remote.take(10), padded)
    }

    @Test
    fun `pad filters downloads out of both halves and respects the size`() {
        val padded = RecommendationFilter.pad(
            remote = listOf("r1", "owned"),
            local = listOf("l1", "l2", "l3"),
            size = 10,
            downloadedIds = setOf("owned", "l2"),
            idOf = { it },
        )

        assertEquals(listOf("r1", "l1", "l3"), padded)
    }

    @Test
    fun `pad returns nothing when everything is downloaded`() {
        val padded = RecommendationFilter.pad(
            remote = listOf("a"),
            local = listOf("b"),
            size = 50,
            downloadedIds = setOf("a", "b"),
            idOf = { it },
        )

        assertEquals(emptyList<String>(), padded)
    }
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
bash /tmp/ktool/run-recommendation-filter-tests.sh /tmp/vivi-reco
```

Expected: compilation failure, `unresolved reference: seedIds` and `unresolved reference: pad`.

- [ ] **Step 3: Write the minimal implementation**

Add to `RecommendationFilter` (after `keepCollection`):

```kotlin
    /**
     * Seeds for the recommendation lookups: the existing play-history seeds unchanged, then downloaded
     * songs that are not already among them, at most `maxDownloaded` of them.
     */
    fun seedIds(playedSeeds: List<String>, downloadedSongs: List<String>, maxDownloaded: Int): List<String> {
        val extra = downloadedSongs
            .filterNot { it in playedSeeds }
            .distinct()
            .take(maxDownloaded.coerceAtLeast(0))
        return playedSeeds + extra
    }

    /**
     * Remote items first, then local items, both filtered and de-duplicated by id, capped at `size`.
     * Used to grow the Covers & Remixes row past whatever the server shelf returned.
     */
    fun <T> pad(
        remote: List<T>,
        local: List<T>,
        size: Int,
        downloadedIds: Set<String>,
        idOf: (T) -> String,
    ): List<T> {
        val limit = clampSize(size)
        val seen = LinkedHashSet<String>()
        val result = mutableListOf<T>()
        for (item in keepUndownloaded(remote, downloadedIds, idOf) + keepUndownloaded(local, downloadedIds, idOf)) {
            if (seen.add(idOf(item))) result.add(item)
            if (result.size == limit) break
        }
        return result
    }
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
bash /tmp/ktool/run-recommendation-filter-tests.sh /tmp/vivi-reco
```

Expected: `OK (16 tests)` and a `RecommendationFilter` line with zero missed lines.

- [ ] **Step 5: Commit**

```bash
cd /tmp/vivi-reco
git add -A
git -c user.email=patch@local -c user.name=patch commit -qm "feat: downloaded seeds and row padding"
```

---

### Task 5: DownloadedIds mapper

**Files:**

- Create: `/tmp/vivi-reco/app/src/main/kotlin/com/music/vivi/playback/DownloadedIds.kt`
- Test: `/tmp/vivi-reco/app/src/test/kotlin/com/music/vivi/playback/DownloadedIdsTest.kt`

- [ ] **Step 1: Write the failing tests**

Create `DownloadedIdsTest.kt`:

```kotlin
/**
 * vivimusic Project (C) 2026
 * Licensed under GPL-3.0 | See git history for contributors
 */

package com.music.vivi.playback

import org.junit.Assert.assertEquals
import org.junit.Test

class DownloadedIdsTest {

    @Test
    fun `completed maps Media3 states onto the finished ids`() {
        val states = mapOf(
            "done" to RecommendationFilter.STATE_COMPLETED,
            "queued" to 0,
            "running" to 2,
            "failed" to 1,
        )

        assertEquals(setOf("done"), DownloadedIds.completed(states))
    }

    @Test
    fun `completed of an empty index is empty`() {
        assertEquals(emptySet<String>(), DownloadedIds.completed(emptyMap()))
    }
}
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
bash /tmp/ktool/run-recommendation-filter-tests.sh /tmp/vivi-reco
```

Expected: compilation failure, `unresolved reference: DownloadedIds`.

- [ ] **Step 3: Write the minimal implementation**

Create `DownloadedIds.kt`:

```kotlin
/**
 * vivimusic Project (C) 2026
 * Licensed under GPL-3.0 | See git history for contributors
 */

package com.music.vivi.playback

/**
 * Bridges Media3's download index to the pure [RecommendationFilter].
 *
 * [DownloadUtil] is a `@Singleton` whose `downloads` flow is a `Map<String, Download>` keyed by the
 * download request id, which is the YouTube video id - the same id every home-screen item carries.
 * HomeViewModel reduces that map to `Map<String, Int>` (id to state) in one line, which keeps Media3
 * types out of this file and out of the unit tests.
 */
object DownloadedIds {

    /** Media3 snapshots for the given id-to-state map. */
    fun snapshots(states: Map<String, Int>): List<RecommendationFilter.DownloadSnapshot> =
        states.map { (id, state) -> RecommendationFilter.DownloadSnapshot(id, state) }

    /** Ids of downloads that finished, ready to hand to the filter. */
    fun completed(states: Map<String, Int>): Set<String> =
        RecommendationFilter.completedIds(snapshots(states))
}
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
bash /tmp/ktool/run-recommendation-filter-tests.sh /tmp/vivi-reco
```

Expected: `OK (18 tests)`, coverage lines for `RecommendationFilter` and `DownloadedIds`, all with zero missed lines.

- [ ] **Step 5: Commit**

```bash
cd /tmp/vivi-reco
git add -A
git -c user.email=patch@local -c user.name=patch commit -qm "feat: Media3 download-state mapper"
```

---

### Task 6: Preference keys

**Files:**

- Create: `/tmp/vivi-reco/app/src/main/kotlin/com/music/vivi/playback/LocalRecommendationPrefs.kt`

- [ ] **Step 1: Write the file**

```kotlin
/**
 * vivimusic Project (C) 2026
 * Licensed under GPL-3.0 | See git history for contributors
 */

package com.music.vivi.playback

import androidx.datastore.preferences.core.intPreferencesKey

/**
 * Preferences owned by the "hide downloads and show more per section" patch.
 *
 * Kept out of `constants/PreferenceKeys.kt` for the same reason as [LocalDownloadPrefs]: that file is
 * touched by nearly every upstream release, and an added line there is the likeliest thing to stop this
 * patch from applying. Defaults live in [RecommendationFilter] so the settings rows and the view model
 * cannot disagree about them.
 */
val QuickPicksSizeKey = intPreferencesKey("localRecommendation.quickPicksSize")

val DailyDiscoverSizeKey = intPreferencesKey("localRecommendation.dailyDiscoverSize")

val CoversAndRemixesSizeKey = intPreferencesKey("localRecommendation.coversAndRemixesSize")
```

- [ ] **Step 2: Verify it matches patch 01's conventions**

```bash
cd /tmp/vivi-reco
diff <(head -8 app/src/main/kotlin/com/music/vivi/playback/LocalDownloadPrefs.kt) \
     <(head -8 app/src/main/kotlin/com/music/vivi/playback/LocalRecommendationPrefs.kt)
```

Expected: only the file-name line in the licence header differs (`LocalDownloadPrefs.kt` vs nothing - the header text
is identical), no other difference in the first eight lines.

- [ ] **Step 3: Commit**

```bash
cd /tmp/vivi-reco
git add -A
git -c user.email=patch@local -c user.name=patch commit -qm "feat: recommendation size preferences"
```

---

### Task 7: Strings and settings group

**Files:**

- Create: `/tmp/vivi-reco/app/src/main/res/values/local_recommendation_strings.xml`
- Create: `/tmp/vivi-reco/app/src/main/kotlin/com/music/vivi/ui/screens/settings/LocalRecommendationSettings.kt`

Component signatures already verified in this codebase (do not invent others):

```text
ExpressiveSettingGroup(title: String? = null, items: List<Material3SettingsItem>,
                      modifier: Modifier = Modifier, itemMinHeight: Dp? = null)
Material3SettingsItem(icon = painterResource(...), title = { Text(...) },
                      trailingContent = { Text(...) }, onClick = { ... })
ActionPromptDialog(title: String? = null, onDismiss: () -> Unit, onConfirm: () -> Unit,
                   onReset: (() -> Unit)? = null, onCancel: (() -> Unit)? = null,
                   content: @Composable ColumnScope.() -> Unit = {})
rememberPreference(key, defaultValue)  // destructured as val (value, setter) = ...
```

Drawable availability, confirmed by running the check in Step 3: `home_outlined`, `explore_outlined` and
`music_note` exist; `discover_outlined` and `remix_outlined` do not, so Step 2's third row uses `music_note`
and its second row uses `explore_outlined`.

- [ ] **Step 1: Write the strings**

Create `local_recommendation_strings.xml`:

```xml
<?xml version="1.0" encoding="utf-8"?>
<!--
  Strings for the "hide downloads and show more per section" patch.
  Kept in their own file so the patch never has to touch vivi_strings.xml, which upstream edits on nearly
  every release.
-->
<resources>
    <string name="recommendations">Recommendations</string>
    <string name="recommendations_quick_picks_items">Quick Picks items</string>
    <string name="recommendations_daily_discover_items">Daily Discover items</string>
    <string name="recommendations_covers_and_remixes_items">Covers &amp; Remixes items</string>
    <string name="recommendations_items_hint">Items per section, 10 to 200. No downloads.</string>
    <string name="recommendations_items_invalid">Enter a whole number between 10 and 200.</string>
</resources>
```

- [ ] **Step 2: Write the settings group**

Create `LocalRecommendationSettings.kt`:

```kotlin
/**
 * vivimusic Project (C) 2026
 * Licensed under GPL-3.0 | See git history for contributors
 */
package com.music.vivi.ui.screens.settings

import androidx.compose.foundation.layout.Column
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import com.music.vivi.R
import com.music.vivi.playback.CoversAndRemixesSizeKey
import com.music.vivi.playback.DailyDiscoverSizeKey
import com.music.vivi.playback.QuickPicksSizeKey
import com.music.vivi.playback.RecommendationFilter
import com.music.vivi.ui.component.ActionPromptDialog
import com.music.vivi.ui.component.ExpressiveSettingGroup
import com.music.vivi.ui.component.Material3SettingsItem
import com.music.vivi.utils.rememberPreference

/** Which of the three sizes the number dialog is currently editing. */
private enum class RecommendationSizeField { QUICK_PICKS, DAILY_DISCOVER, COVERS_AND_REMIXES }

/**
 * Settings rows for the "hide downloads and show more per section" patch.
 *
 * The group is called from upstream ContentSettings.kt with a single line, so the patch touches as little
 * upstream code as possible.
 */
@Composable
fun LocalRecommendationSettingsGroup() {
    val (quickPicksSize, onQuickPicksSizeChange) =
        rememberPreference(QuickPicksSizeKey, RecommendationFilter.DEFAULT_SECTION_SIZE)
    val (dailyDiscoverSize, onDailyDiscoverSizeChange) =
        rememberPreference(DailyDiscoverSizeKey, RecommendationFilter.DEFAULT_SECTION_SIZE)
    val (coversAndRemixesSize, onCoversAndRemixesSizeChange) =
        rememberPreference(CoversAndRemixesSizeKey, RecommendationFilter.DEFAULT_SECTION_SIZE)

    var editing by remember { mutableStateOf<RecommendationSizeField?>(null) }
    var draft by remember { mutableStateOf("") }

    fun open(field: RecommendationSizeField, current: Int) {
        editing = field
        draft = current.toString()
    }

    /** Returns the parsed size, or null when the text is not a number inside the supported range. */
    fun parsed(text: String): Int? {
        val value = text.trim().toIntOrNull() ?: return null
        return value.takeIf { it in RecommendationFilter.MIN_SECTION_SIZE..RecommendationFilter.MAX_SECTION_SIZE }
    }

    ExpressiveSettingGroup(
        title = stringResource(R.string.recommendations),
        items = listOf(
            Material3SettingsItem(
                icon = painterResource(R.drawable.home_outlined),
                title = { Text(stringResource(R.string.recommendations_quick_picks_items)) },
                trailingContent = { Text(quickPicksSize.toString()) },
                onClick = { open(RecommendationSizeField.QUICK_PICKS, quickPicksSize) },
            ),
            Material3SettingsItem(
                icon = painterResource(R.drawable.discover_outlined),
                title = { Text(stringResource(R.string.recommendations_daily_discover_items)) },
                trailingContent = { Text(dailyDiscoverSize.toString()) },
                onClick = { open(RecommendationSizeField.DAILY_DISCOVER, dailyDiscoverSize) },
            ),
            Material3SettingsItem(
                icon = painterResource(R.drawable.remix_outlined),
                title = { Text(stringResource(R.string.recommendations_covers_and_remixes_items)) },
                trailingContent = { Text(coversAndRemixesSize.toString()) },
                onClick = { open(RecommendationSizeField.COVERS_AND_REMIXES, coversAndRemixesSize) },
            ),
        ),
    )

    val field = editing
    if (field != null) {
        ActionPromptDialog(
            title = stringResource(R.string.recommendations),
            onDismiss = { editing = null },
            onConfirm = {
                val value = parsed(draft)
                if (value != null) {
                    when (field) {
                        RecommendationSizeField.QUICK_PICKS -> onQuickPicksSizeChange(value)
                        RecommendationSizeField.DAILY_DISCOVER -> onDailyDiscoverSizeChange(value)
                        RecommendationSizeField.COVERS_AND_REMIXES -> onCoversAndRemixesSizeChange(value)
                    }
                    editing = null
                }
            },
            onReset = { draft = RecommendationFilter.DEFAULT_SECTION_SIZE.toString() },
            onCancel = { editing = null },
        ) {
            Column {
                OutlinedTextField(
                    value = draft,
                    onValueChange = { draft = it },
                    label = { Text(stringResource(R.string.recommendations_items_hint)) },
                    isError = parsed(draft) == null,
                    supportingText = {
                        if (parsed(draft) == null) Text(stringResource(R.string.recommendations_items_invalid))
                    },
                )
            }
        }
    }
}
```

- [ ] **Step 3: Confirm every icon and helper actually exists before moving on**

```bash
cd /tmp/vivi-reco
for name in home_outlined discover_outlined remix_outlined; do
  printf '%-18s ' "$name"
  ls app/src/main/res/drawable/${name}.xml >/dev/null 2>&1 && echo present || echo "MISSING - pick another drawable"
done
grep -rn "fun rememberPreference" app/src/main/kotlin/com/music/vivi/utils/DataStore.kt
grep -rn "class Material3SettingsItem\|data class Material3SettingsItem" \
  app/src/main/kotlin/com/music/vivi/ui/component/*.kt | head -3
```

Expected: all three drawables `present`, `rememberPreference` found with its `(key, defaultValue)` parameters, and
`Material3SettingsItem` found. If a drawable is missing, substitute one that exists (for example `home_outlined` for
all three) - do not invent a resource name.

- [ ] **Step 4: Commit**

```bash
cd /tmp/vivi-reco
git add -A
git -c user.email=patch@local -c user.name=patch commit -qm "feat: recommendation size settings group"
```

---

### Task 8: HomeViewModel hook A - injected download state and the local rows

**Files:**

- Modify: `/tmp/vivi-reco/app/src/main/kotlin/com/music/vivi/viewmodels/HomeViewModel.kt:521-541` (constructor and
  `loadLocalDataPhase`)

- [ ] **Step 1: Inject DownloadUtil**

Change the constructor (currently takes `context`, `database`, `syncUtils`, `wrappedManager`, `wrappedAudioService`) to
add one parameter at the end:

```kotlin
@HiltViewModel
class HomeViewModel @Inject constructor(
    @ApplicationContext val context: Context,
    val database: MusicDatabase,
    val syncUtils: SyncUtils,
    val wrappedManager: WrappedManager,
    private val wrappedAudioService: WrappedAudioService,
    private val downloadUtil: DownloadUtil,
) : ViewModel() {
```

Add the import next to the other `com.music.vivi.playback` imports:

```kotlin
import com.music.vivi.playback.DownloadUtil
import com.music.vivi.playback.DownloadedIds
import com.music.vivi.playback.RecommendationFilter
import com.music.vivi.playback.QuickPicksSizeKey
import com.music.vivi.playback.DailyDiscoverSizeKey
import com.music.vivi.playback.CoversAndRemixesSizeKey
```

- [ ] **Step 2: Read the sizes and download ids once, then filter the local rows**

In `loadLocalDataPhase()`, immediately after `val hideVideoSongs = context.dataStore.get(HideVideoSongsKey, false)`,
insert:

```kotlin
        quickPicksSize = sectionSize(QuickPicksSizeKey)
        dailyDiscoverSize = sectionSize(DailyDiscoverSizeKey)
        coversAndRemixesSize = sectionSize(CoversAndRemixesSizeKey)
        downloadedIds = DownloadedIds.completed(downloadUtil.downloads.value.mapValues { it.value.state })
```

(the four fields are declared in Step 3; the task's syntax check at Step 4 covers the whole file at once)

Then replace the two assignment lines that build `forgottenFavorites` and `keepListening` with filtered,
downloaded-aware versions:

```kotlin
        forgottenFavorites.value = RecommendationFilter
            .keepUndownloaded(database.forgottenFavorites().first(), downloadedIds) { it.id }
            .filterVideoSongs(hideVideoSongs)
            .shuffled()
            .take(20)
```

and, for the keep-listening block, wrap each list before combining:

```kotlin
        val keepListeningSongs = RecommendationFilter
            .keepUndownloaded(
                database.mostPlayedSongs(fromTimeStamp, limit = 15, offset = 5).first(),
                downloadedIds,
            ) { it.id }
            .filterVideoSongs(hideVideoSongs)
            .shuffled()
            .take(10)
        val keepListeningAlbums = keepSuggestible(
            database.mostPlayedAlbums(fromTimeStamp, limit = 8, offset = 2).first(),
            downloadedIds,
        )
            .filter { (it as? Album)?.album?.thumbnailUrl != null }
            .shuffled()
            .take(5)
        val keepListeningArtists = RecommendationFilter
            .keepUndownloaded(database.mostPlayedArtists(fromTimeStamp).first(), downloadedIds) { it.id }
            .filter { it.artist.isYouTubeArtist && it.artist.thumbnailUrl != null }
            .shuffled()
            .take(5)
```

- [ ] **Step 3: Declare the fields and the two small helpers**

Add four private fields next to the existing section `MutableStateFlow`s (near `val quickPicks`,
`val coversAndRemixes`):

```kotlin
    private var quickPicksSize = RecommendationFilter.DEFAULT_SECTION_SIZE
    private var dailyDiscoverSize = RecommendationFilter.DEFAULT_SECTION_SIZE
    private var coversAndRemixesSize = RecommendationFilter.DEFAULT_SECTION_SIZE
    private var downloadedIds: Set<String> = emptySet()
```

Add these two private helpers next to them. `sectionSize` clamps the stored value and falls back to the
default when DataStore cannot be read; `keepSuggestible` applies both halves of the spec's rule - drop
songs that are downloaded, and drop an album card only when every track it contains is downloaded:

```kotlin
    /** Configured section size, clamped, falling back to the default when DataStore cannot be read. */
    private suspend fun sectionSize(key: Preferences.Key<Int>): Int =
        runCatching { context.dataStore.get(key, RecommendationFilter.DEFAULT_SECTION_SIZE) }
            .getOrDefault(RecommendationFilter.DEFAULT_SECTION_SIZE)
            .let { RecommendationFilter.clampSize(it) }

    /** Drops downloaded songs, and album cards whose every track is already downloaded. */
    private suspend fun keepSuggestible(items: List<YTItem>, downloaded: Set<String>): List<YTItem> {
        val kept = mutableListOf<YTItem>()
        for (item in items) {
            if (item.id in downloaded) continue
            if (item is Album) {
                val trackIds = database.albumSongs(item.id).first().map { it.id }
                if (!RecommendationFilter.keepCollection(trackIds, downloaded)) continue
            }
            kept.add(item)
        }
        return kept
    }
```

Make sure `import androidx.datastore.preferences.core.Preferences` and `import com.music.vivi.db.entities.Album`
are present (check with
`grep -n "import com.music.vivi.db.entities.Album" app/src/main/kotlin/com/music/vivi/viewmodels/HomeViewModel.kt`
and add them if missing).

Note: `loadLocalDataPhase()` runs in the local phase, which always precedes `loadNetworkDataPhase()` in
`load()`, so the fields are populated before any network section reads them.

- [ ] **Step 4: Verify the file still parses as Kotlin (syntax only)**

```bash
cd /tmp/vivi-reco
/tmp/ktool/kotlinc2310/kotlinc/bin/kotlinc -Xallow-any-scripts-in-source-roots -nowarn -d /tmp/ktool/syntax-out \
  app/src/main/kotlin/com/music/vivi/viewmodels/HomeViewModel.kt 2>&1 | head -5
```

Expected: errors about unresolved Android/Hilt/Media3 references (that is expected without the Android SDK) but **no
syntax errors** such as `expecting '}'` or `unexpected token`. If you see a syntax error, fix it before continuing.

- [ ] **Step 5: Commit**

```bash
cd /tmp/vivi-reco
git add -A
git -c user.email=patch@local -c user.name=patch commit -qm "feat: filter local home rows by downloads"
```

---

### Task 9: HomeViewModel hook B - Quick Picks

**Files:**

- Modify: `/tmp/vivi-reco/app/src/main/kotlin/com/music/vivi/viewmodels/HomeViewModel.kt:377-420` (`getQuickPicks`)

- [ ] **Step 1: Add the downloaded-seed lookups**

In `getQuickPicks()`, after the block that builds `ytSimilarSongs` from `recentSong`, insert:

```kotlin
                // Downloaded songs the user has not played recently are a strong signal too: pull their
                // related songs as extra candidates. seedIds bounds this to MAX_DOWNLOAD_SEEDS ids BEFORE the
                // database lookup, which keeps the SQL IN list small.
                val downloadSeedIds = RecommendationFilter
                    .seedIds(
                        playedSeeds = listOfNotNull(recentSong?.id),
                        downloadedSongs = downloadedIds.toList(),
                        maxDownloaded = RecommendationFilter.MAX_DOWNLOAD_SEEDS,
                    )
                    .filterNot { it == recentSong?.id }
                val downloadSeeds = database.getSongsByIds(downloadSeedIds)
                val ytDownloadRelated = mutableListOf<Song>()
                for (seed in downloadSeeds) {
                    YouTube.next(WatchEndpoint(videoId = seed.id)).getOrNull()?.relatedEndpoint?.let { endpoint ->
                        YouTube.related(endpoint).onSuccess { page ->
                            page.songs.take(10).forEach { ytSong ->
                                database.song(ytSong.id).first()?.let { localSong ->
                                    if (!hideVideoSongs || !localSong.song.isVideo) {
                                        ytDownloadRelated.add(localSong)
                                    }
                                }
                            }
                        }
                    }
                }
```

- [ ] **Step 2: Filter the row and use the configured size**

Replace the combine-and-take block (currently `.distinctBy { it.id }.shuffled().take(20)` and the `ifEmpty` fallback)
with:

```kotlin
                // Combine all sources, drop what is already downloaded, then fill to the configured size.
                val combined = RecommendationFilter
                    .keepUndownloaded(
                        relatedSongs + forgotten + ytSimilarSongs + ytDownloadRelated,
                        downloadedIds,
                    ) { it.id }
                    .distinctBy { it.id }
                    .shuffled()
                    .take(quickPicksSize)

                quickPicks.value = combined.ifEmpty {
                    RecommendationFilter
                        .keepUndownloaded(relatedSongs, downloadedIds) { it.id }
                        .shuffled()
                        .take(quickPicksSize)
                }
```

And in the `QuickPicks.LAST_LISTEN` branch, replace the single assignment with:

```kotlin
                    quickPicks.value = RecommendationFilter
                        .keepUndownloaded(database.getRelatedSongs(song.id).first(), downloadedIds) { it.id }
                        .filterVideoSongs(hideVideoSongs)
                        .shuffled()
                        .take(quickPicksSize)
```

- [ ] **Step 3: Verify syntax as in Task 8 Step 4**

```bash
cd /tmp/vivi-reco
/tmp/ktool/kotlinc2310/kotlinc/bin/kotlinc -Xallow-any-scripts-in-source-roots -nowarn -d /tmp/ktool/syntax-out \
  app/src/main/kotlin/com/music/vivi/viewmodels/HomeViewModel.kt 2>&1 | grep -E "expecting|unexpected token" | head -5
```

Expected: no output (unresolved references are fine, syntax errors are not).

- [ ] **Step 4: Commit**

```bash
cd /tmp/vivi-reco
git add -A
git -c user.email=patch@local -c user.name=patch commit -qm "feat: quick picks filter, seeds and size"
```

---

### Task 10: HomeViewModel hook C - Daily Discover

**Files:**

- Modify: `/tmp/vivi-reco/app/src/main/kotlin/com/music/vivi/viewmodels/HomeViewModel.kt:289-376` (`getDailyDiscover`)

- [ ] **Step 1: Extend the seeds with downloaded songs**

In `getDailyDiscover()`, after the existing `seeds` fallback chain (the block that ends with the backend
fallback for new users), insert:

```kotlin
        // Add downloaded songs that are not already seeds, so a downloaded-but-unplayed track also drives
        // the mix. Bounded by RecommendationFilter.MAX_DOWNLOAD_SEEDS.
        val playedSeedIds = seeds.map { it.id }
        val downloadedSeedIds = RecommendationFilter
            .seedIds(
                playedSeeds = emptyList(),
                downloadedSongs = downloadedIds.toList(),
                maxDownloaded = RecommendationFilter.MAX_DOWNLOAD_SEEDS,
            )
            .filterNot { it in playedSeedIds }
        if (downloadedSeedIds.isNotEmpty()) {
            val extraSeeds = database.getSongsByIds(downloadedSeedIds)
            seeds = (seeds + extraSeeds).distinctBy { it.id }
        }
```

- [ ] **Step 2: Filter the finished list and cap it**

Replace the final assignment (currently
`val finalizedItems = items.toList().distinctBy { it.recommendation.id }.shuffled()` followed by
`dailyDiscover.value = finalizedItems`) with:

```kotlin
        val finalizedItems = RecommendationFilter
            .keepUndownloaded(items.toList(), downloadedIds) { it.recommendation.id }
            .distinctBy { it.recommendation.id }
            .shuffled()
            .take(dailyDiscoverSize)
        android.util.Log.d("DailyDiscover", "Finalized dailyDiscover items size: ${finalizedItems.size}")
        dailyDiscover.value = finalizedItems
```

- [ ] **Step 3: Verify syntax**

```bash
cd /tmp/vivi-reco
/tmp/ktool/kotlinc2310/kotlinc/bin/kotlinc -Xallow-any-scripts-in-source-roots -nowarn -d /tmp/ktool/syntax-out \
  app/src/main/kotlin/com/music/vivi/viewmodels/HomeViewModel.kt 2>&1 | grep -E "expecting|unexpected token" | head -5
```

Expected: no output.

- [ ] **Step 4: Commit**

```bash
cd /tmp/vivi-reco
git add -A
git -c user.email=patch@local -c user.name=patch commit -qm "feat: daily discover filter, seeds and size"
```

---

### Task 11: HomeViewModel hook D - Covers & Remixes shelf, padding and fallback

**Files:**

- Modify: `/tmp/vivi-reco/app/src/main/kotlin/com/music/vivi/viewmodels/HomeViewModel.kt` (`loadNetworkDataPhase`
  covers block at 624-676, `loadFallbackCoversAndRemixes` at 689-712)

- [ ] **Step 1: Filter the remote shelf and pad it when it is short**

Replace the covers-shelf block inside `loadNetworkDataPhase()` (the `cnrSection` handling) with a version
that filters and then pads from the fallback when the filtered shelf is shorter than the configured size:

```kotlin
                YouTube.home().onSuccess { page ->
                    val cnrSection = page.sections.find {
                        it.title.contains("cover", true) && it.title.contains("remix", true)
                    }
                    val shelfItems = cnrSection?.items.orEmpty()
                        .filterExplicit(hideExplicit)
                        .filterYoutubeShorts(hideYoutubeShorts)

                    if (shelfItems.size < coversAndRemixesSize) {
                        // The shelf is server-sized and usually shorter than the configured count, so top it up
                        // from the local fallback builder before showing it.
                        val localItems = buildFallbackCoversAndRemixes()
                        val padded = RecommendationFilter.pad(
                            remote = shelfItems,
                            local = localItems,
                            size = coversAndRemixesSize,
                            downloadedIds = downloadedIds,
                            idOf = { it.id },
                        )
                        if (padded.isNotEmpty()) {
                            coversAndRemixes.value = HomePage.Section(
                                title = cnrSection?.title ?: "Covers and remixes",
                                label = cnrSection?.label,
                                thumbnail = cnrSection?.thumbnail,
                                endpoint = null,
                                items = padded,
                            )
                        }
                    } else {
                        coversAndRemixes.value = cnrSection?.copy(
                            items = RecommendationFilter
                                .keepUndownloaded(shelfItems, downloadedIds) { it.id }
                                .take(coversAndRemixesSize),
                        )
                    }

                    homePage.value = page.copy(
                        sections = page.sections.mapNotNull { section ->
                            if (section == cnrSection) return@mapNotNull null
```

(the rest of that `homePage.value = page.copy(...)` block stays exactly as it is)

- [ ] **Step 2: Turn the fallback builder into a reusable function**

Replace `loadFallbackCoversAndRemixes()`'s body with a pure builder plus a thin caller:

```kotlin
    /** Builds covers/remixes candidates locally. Returns an empty list when the lookup fails. */
    private suspend fun buildFallbackCoversAndRemixes(): List<YTItem> {
        var built: List<YTItem> = emptyList()
        YouTube.searchSummary("music covers and remixes").onSuccess { result ->
            val songs = result.summaries.find { it.title == "Songs" }?.items?.filterIsInstance<SongItem>().orEmpty()
            val videos = result.summaries.find { it.title == "Videos" }?.items?.filterIsInstance<SongItem>().orEmpty()
            built = (songs + videos)
                .filter { !it.musicVideoType.toString().contains("PODCAST", ignoreCase = true) }
                .filter { (it.duration ?: 0) < 600 }
                .distinctBy { it.id }
                .shuffled()
        }.onFailure { reportException(it) }
        return built
    }

    private suspend fun loadFallbackCoversAndRemixes() {
        val items = buildFallbackCoversAndRemixes()
        if (items.isNotEmpty()) {
            coversAndRemixes.value = HomePage.Section(
                title = "Covers and remixes",
                label = null,
                thumbnail = null,
                endpoint = null,
                items = RecommendationFilter
                    .keepUndownloaded(items, downloadedIds) { it.id }
                    .take(coversAndRemixesSize),
            )
        }
    }
```

Note: this function keeps the app's existing error convention (`.onSuccess` / `.onFailure { reportException(it) }`),
so a failed lookup yields an empty list rather than an exception.

- [ ] **Step 3: Seed the fallback searches from downloads when the row still needs items**

This is the "related padding" the spec asks for. At the end of Step 1's padding branch, after
`buildFallbackCoversAndRemixes()`, extend the local list with seeded searches before calling `pad`:

```kotlin
                        val seedIds = RecommendationFilter.seedIds(
                            playedSeeds = database.mostPlayedSongs(
                                System.currentTimeMillis() - 86400000L * 7 * 4,
                                limit = 3,
                            )
                                .first().map { it.id },
                            downloadedSongs = downloadedIds.toList(),
                            maxDownloaded = 3,
                        ).take(3)
                        val seededItems = buildSeededCoversAndRemixes(seedIds)
                        val localItems = buildFallbackCoversAndRemixes() + seededItems
```

and add the new helper next to the fallback builder:

```kotlin
    /** Runs one bounded search per seed, keeping songs that are not podcast-like. */
    private suspend fun buildSeededCoversAndRemixes(seedIds: List<String>): List<YTItem> {
        val found = mutableListOf<YTItem>()
        for (songId in seedIds) {
            val song = database.song(songId).first()?.song ?: continue
            val artist = song.artists.firstOrNull()?.name ?: continue
            YouTube.searchSummary("$artist cover remix").onSuccess { result ->
                val items = result.summaries.find { it.title == "Songs" }?.items?.filterIsInstance<SongItem>().orEmpty()
                found.addAll(items.filter { (it.duration ?: 0) < 600 })
            }.onFailure { reportException(it) }
        }
        return found.distinctBy { it.id }
    }
```

- [ ] **Step 4: Verify syntax**

```bash
cd /tmp/vivi-reco
/tmp/ktool/kotlinc2310/kotlinc/bin/kotlinc -Xallow-any-scripts-in-source-roots -nowarn -d /tmp/ktool/syntax-out \
  app/src/main/kotlin/com/music/vivi/viewmodels/HomeViewModel.kt 2>&1 | grep -E "expecting|unexpected token" | head -5
```

Expected: no output.

- [ ] **Step 5: Commit**

```bash
cd /tmp/vivi-reco
git add -A
git -c user.email=patch@local -c user.name=patch commit -qm "feat: covers and remixes filtering and padding"
```

---

### Task 12: HomeViewModel hook E - Similar Recommendations

**Files:**

- Modify: `/tmp/vivi-reco/app/src/main/kotlin/com/music/vivi/viewmodels/HomeViewModel.kt:615`
  (`loadSimilarRecommendations`)

- [ ] **Step 1: Filter each recommendation's items and drop the empty ones**

Replace:

```kotlin
            similarRecommendations.value = results.filterNotNull().shuffled()
```

with:

```kotlin
            similarRecommendations.value = results
                .filterNotNull()
                .map { recommendation ->
                    recommendation.copy(items = keepSuggestible(recommendation.items, downloadedIds))
                }
                .filter { it.items.isNotEmpty() }
                .shuffled()
```

- [ ] **Step 2: Verify syntax**

```bash
cd /tmp/vivi-reco
/tmp/ktool/kotlinc2310/kotlinc/bin/kotlinc -Xallow-any-scripts-in-source-roots -nowarn -d /tmp/ktool/syntax-out \
  app/src/main/kotlin/com/music/vivi/viewmodels/HomeViewModel.kt 2>&1 | grep -E "expecting|unexpected token" | head -5
```

Expected: no output.

- [ ] **Step 3: Commit**

```bash
cd /tmp/vivi-reco
git add -A
git -c user.email=patch@local -c user.name=patch commit -qm "feat: filter similar recommendations"
```

---

### Task 13: ContentSettings hook

**Files:**

- Modify: `/tmp/vivi-reco/app/src/main/kotlin/com/music/vivi/ui/screens/settings/ContentSettings.kt` (after the group
  holding the Quick Picks row)

- [ ] **Step 1: Find the exact insertion point**

```bash
cd /tmp/vivi-reco
grep -n "set_quick_picks" -A 16 app/src/main/kotlin/com/music/vivi/ui/screens/settings/ContentSettings.kt | head -20
```

Expected: the `Material3SettingsItem` block that renders the Quick Picks row, inside a group, followed by a
`Spacer(modifier = Modifier.height(27.dp))`. The insertion point is immediately after that group's closing
parenthesis and before that `Spacer`.

- [ ] **Step 2: Insert the single call**

Add exactly this line at that point (indentation must match the surrounding statements):

```kotlin
        LocalRecommendationSettingsGroup()
```

Add the import with the other screen imports:

```kotlin
import com.music.vivi.ui.screens.settings.LocalRecommendationSettingsGroup
```

(the call is in the same package, so the import is optional; keep it only if the file already imports sibling
composables that way)

- [ ] **Step 3: Verify only one line changed in this file**

```bash
cd /tmp/vivi-reco
git diff --stat app/src/main/kotlin/com/music/vivi/ui/screens/settings/ContentSettings.kt
```

Expected: `1 insertion(+)` (plus an import line if you kept it).

- [ ] **Step 4: Commit**

```bash
cd /tmp/vivi-reco
git add -A
git -c user.email=patch@local -c user.name=patch commit -qm "feat: settings entry for recommendation sizes"
```

---

### Task 14: Coverage allowlist

**Files:**

- Modify: `/tmp/vivi-reco/app/build.gradle.kts` (inside patch 01's `kover { }` block)

This is the one addition beyond the spec's two-file contact list: without it, CI's `koverVerify` gate does
not measure the new pure code at all. Two lines, following patch 01's own style.

- [ ] **Step 1: Add the include and the exclude**

```bash
cd /tmp/vivi-reco
grep -n "DownloadRecovery\*\|DownloadRecoveryTest" app/build.gradle.kts
```

Add next to `classes("com.music.vivi.playback.DownloadRecovery*")` in `includes`:

```kotlin
                classes("com.music.vivi.playback.RecommendationFilter*")
                classes("com.music.vivi.playback.DownloadedIds*")
```

and next to the matching test classes in `excludes`:

```kotlin
                classes("com.music.vivi.playback.RecommendationFilterTest")
                classes("com.music.vivi.playback.DownloadedIdsTest")
```

- [ ] **Step 2: Confirm the change is exactly four added lines**

```bash
cd /tmp/vivi-reco
git diff app/build.gradle.kts | grep -c '^+[^+]'
```

Expected: `4`. (Count `+` lines that are not the `+++ b/app/build.gradle.kts` header - a plain `'^+'` counts the header
too and returns 5.)

- [ ] **Step 3: Commit**

```bash
cd /tmp/vivi-reco
git add -A
git -c user.email=patch@local -c user.name=patch commit -qm "test: measure the new pure classes in CI"
```

---

### Task 15: Generate, verify and commit patch 02

**Files:**

- Create: `/data/forks/vivi-music/local-patches/02-recommendations.patch`

- [ ] **Step 1: Re-run the full local test suite one last time**

```bash
bash /tmp/ktool/run-recommendation-filter-tests.sh /tmp/vivi-reco
bash /tmp/ktool/run-album-artist-tests.sh /tmp/vivi-reco
```

Expected: both suites report `OK` with no failures, and the coverage lines show zero missed lines for
`RecommendationFilterKt` and `DownloadedIds`.

- [ ] **Step 2: Generate the patch from the base commit**

```bash
cd /tmp/vivi-reco
BASE=$(git rev-list --max-parents=0 HEAD | tail -1)
# the base commit is the one this plan created as "base: upstream + patch 01"
BASE=$(git log --format=%H --grep="base: upstream + patch 01" -1)
git diff --binary --abbrev=8 "$BASE" HEAD > /tmp/02-recommendations.patch
grep -c '^diff --git' /tmp/02-recommendations.patch
grep '^diff --git' /tmp/02-recommendations.patch | sed 's|diff --git a/||; s| b/.*||'
```

Expected: the file list is exactly the seven created files plus the three modified upstream files from the
File map, and nothing else. If anything else appears, stop and find out why before installing the patch.

- [ ] **Step 3: Install the patch and prove it applies to a fresh upstream clone**

```bash
cp /tmp/02-recommendations.patch /data/forks/vivi-music/local-patches/02-recommendations.patch
rm -rf /tmp/upstream-check3
git clone --depth 1 --quiet https://github.com/vivizzz007/vivi-music /tmp/upstream-check3
cd /tmp/upstream-check3
/data/forks/vivi-music/local-patches/apply.sh --check
```

Expected: `OK   01-download-folder.patch (applies)`, `OK   02-recommendations.patch (applies)`,
`OK   pinned debug keystore present`.

- [ ] **Step 4: Prove the patch does not rewrite patch 01's work**

```bash
cd /tmp/vivi-reco
git diff --stat "$BASE" HEAD -- app/src/main/kotlin/com/music/vivi/playback/DownloadUtil.kt \
  app/src/main/kotlin/com/music/vivi/playback/DownloadFolderExporter.kt \
  local-patches/README.md
```

Expected: no output (patch 02 must not touch patch 01's files or the README's existing text).

- [ ] **Step 5: Commit the patch**

```bash
cd /data/forks/vivi-music
git add local-patches/02-recommendations.patch
git commit -q -m "local: hide downloaded music and size the home recommendation rows"
git show --stat --oneline HEAD | head -5
```

Expected: one file added, no upstream file in the commit.

---

### Task 16: Documentation

**Files:**

- Modify: `/data/forks/vivi-music/local-patches/README.md`

- [ ] **Step 1: Add a patch 02 section**

Append a section in the same style as the existing patch 01 description, with this content:

```markdown
## What patch 02 does

`02-recommendations.patch` stops the home-screen recommendation rows suggesting music you already own and
lets you decide how much they show:

- Quick Picks, Your Daily Discovery and Covers & Remixes hide anything already downloaded. Similar
  Recommendations, Keep Listening and Forgotten Favorites are filtered the same way.
- Downloaded songs are added to the seeds of Quick Picks and Daily Discover, so a downloaded but unplayed
  track also pulls in related music.
- Covers & Remixes keeps YouTube's own shelf first, then pads the row from local cover/remix searches so it
  reaches the configured size.
- Three settings under *Settings -> Content -> Recommendations* set the item count for each of the three
  sections (10 to 200, default 50).
- Only downloads in Media3's completed state count as downloaded; album and playlist cards are hidden only
  when every track they contain is downloaded, and a section that ends up with nothing is not shown.

Upstream files touched: `viewmodels/HomeViewModel.kt` (short hooks), `ui/screens/settings/ContentSettings.kt`
(one line) and `app/build.gradle.kts` (four lines inside patch 01's Kover block).
```

- [ ] **Step 2: Confirm the README's patch 01 text is untouched**

```bash
cd /data/forks/vivi-music
git diff --stat local-patches/README.md
git diff local-patches/README.md | grep -c '^-[^-]'
```

Expected: insertions only, and `0` removed lines.

- [ ] **Step 3: Commit**

```bash
cd /data/forks/vivi-music
git add local-patches/README.md
git commit -q -m "local(docs): describe the recommendations patch"
git log --oneline -3
```

---

### Task 17: Final verification and handoff

- [ ] **Step 1: Run every local gate that can run here**

```bash
cd /data/forks/vivi-music
bash /tmp/ktool/run-recommendation-filter-tests.sh /tmp/vivi-reco
bash /tmp/ktool/run-album-artist-tests.sh /tmp/vivi-reco
local-patches/tests/test-signing-key-stability.sh
```

Expected: all suites pass; the signing-key suite still reports `16 passed, 0 failed, 0 pending`.

- [ ] **Step 2: Confirm the working tree contains only intended changes**

```bash
cd /data/forks/vivi-music
git status --short
git log --oneline -4
```

Expected: the new patch and README commits are present, and no upstream file appears as modified.

- [ ] **Step 3: State the residual honestly in the handoff**

Write in the completion report: the pure rules (14 filter tests plus 2 mapper tests) are verified locally
with JUnit and JaCoCo; the Compose settings group and every `HomeViewModel` hook compile only in CI, because
this machine has JDK 11 and no Android SDK. The `Local Patch Build` run on the pushed commit is the first
real proof that the hooks compile and that `koverVerify` passes.

---

## Self-review notes for the implementer

- The pure files carry no Android imports on purpose. If you find yourself importing `android.` or
  `androidx.media3.` into `RecommendationFilter.kt` or `DownloadedIds.kt`, the design has drifted - stop and
  re-read Task 5.
- Every size flows through `RecommendationFilter.clampSize`, including values already stored in DataStore,
  so a hand-edited preference cannot produce a 0-item or 10 000-item row.
- Never pad a row with downloaded items. If filtering leaves fewer items than the target, the row is simply
  shorter.

## Tech-debt pass (2026-09-26)

Results of the mandated Common checks (no Python or Rust changed, so only the Common section ran):

1. **Test overlap:** the sixteen new unit tests were reviewed for redundancy; the `resize` pair was removed
   later, see item 3.
2. **Coverage:** the changed pure Kotlin is at 100% line coverage (RecommendationFilter 16/16,
   DownloadSnapshot 1/1, DownloadedIds 2/2, branches 14/14 before the removal), and CI's Kover gate of 95%
   measures those classes because patch 02 adds `RecommendationFilter*` and `DownloadedIds*` to the filter.
3. **Dead code (maintainer-approved):** `RecommendationFilter.resize` had no production call site - the hooks
   call `.take()` on an already-clamped size and `pad` clamps internally - so it and its two tests were
   deleted, and the spec's Pure API table no longer lists it. `RecommendationFilterTest` now holds 14 tests.
4. **Docstring audit (subagent, 28 comments reviewed):** three stale comments of patch 02's own making were
   corrected - `pad`'s "capped at `size`" became "capped at the clamped `size`";
   `buildSeededCoversAndRemixes`'s "keeping songs that are not podcast-like" became "keeping only songs
   shorter than ten minutes", because the method applies no type filter; and the Quick Picks seed comment's
   "has not played recently" became "other than the most recent play". Nothing was stale in `DownloadedIds.kt`,
   `LocalRecommendationPrefs.kt`, `LocalRecommendationSettings.kt` or `ContentSettings.kt`.
5. **Recorded, not changed:** `buildSeededCoversAndRemixes` does not apply the PODCAST filter its sibling
   `buildFallbackCoversAndRemixes` applies, so a podcast-typed result under ten minutes can reach the seeded
   covers padding. That is a behaviour question for the review steps, not a doc fix, and was fixed in review
   round 2: the seeded searches now apply the same PODCAST filter.
   The same applies to two pre-existing upstream comments that read "always has something to show on launch"
   and "Guarantees the UI shows real content before any network call": with every item in a section already
   downloaded the section is empty by design (the spec says an empty section is not rendered), so those
   absolutes are no longer true in that case. Upstream prose was left untouched to keep patch 02 small.
6. **README:** patch 02's own section claimed "short hooks" for a 245-line change, and its named-debt list
   predated patch 02; both corrected, and the measured-scope bullet now records the new classes' 100%.

## Code review round 1 (2026-09-26)

Reviewer A: BLOCK - 3 P1, 8 P2, notes. Reviewer B: OK with notes - 8 P2. Thirteen unique issues, all fixed:

**P1:** (1) `getSongsByIds(emptyList())` ran on every refresh without downloads - Room expands it to `IN ()`,
which SQLite rejects - now guarded by `downloadSeedIds.isNotEmpty()`; (2) padded local covers items bypassed
`filterExplicit`/`filterYoutubeShorts`, so most of a 50-item row ignored those settings - the local half is
filtered now; (3) the covers top-up ran up to four serial network searches before `homePage.value` published,
delaying the whole feed - the filtered shelf is published immediately and the top-up runs in a launched
coroutine.

**P2:** (4) covers seeds were played-first so downloaded seeds never ran - downloads are the seeds now, with
played ids filling the rest of the three-seed budget; (5) Daily Discover applied its cap before excluding
played ids, so already-seeded downloads crowded out new ones - the played ids are passed into `seedIds`;
(6) the dead `loadFallbackCoversAndRemixes` was deleted; (7) `loadMoreYouTubeItems` now applies
`take(coversAndRemixesSize)`; (8) the Quick Picks per-seed lookups run concurrently instead of serially, and
the generic covers search only runs when the seeded searches returned nothing; (9) the no-op artist filter
(YouTube channel ids compared against video ids) was dropped, and both `keepSuggestible*` helpers short-circuit
when nothing is downloaded instead of querying `albumSongs` per card on every refresh; (10) the README and this
spec no longer claim playlist-card filtering, the spec's stepper wording, its "no other upstream file" claim and
its 10-20 line sizing were corrected; (11) the signing suite clones into a staging directory and moves it into
place, so an interrupted clone cannot poison the cache, and `UPSTREAM_TREE` lets a caller supply the tree;
(12) `STATE_COMPLETED` is now aliased from patch 01's `MEDIA3_STATE_COMPLETED` rather than duplicated - patch 02
therefore touches that fork-owned file, which the local harness now compiles too; (13) the settings dialog's
state uses `rememberSaveable`.

Notes also fixed: the test fixture labelled state 1 "failed" (Media3's STATE_FAILED is 4; 1 is STATE_STOPPED);
the hint string no longer doubles as the field label and the field asks for a numeric keyboard; and the stray
tracked file `et --hard 33c82f9` was removed from the fork.

## Code review round 2 (2026-09-26)

Both reviewers confirmed all thirteen round-1 fixes in the current code. Reviewer A: BLOCK - 1 P1, 5 P2.
Reviewer B: OK with notes - 6 P2. Eight unique issues, all fixed:

**P1:** the "Daily Discover items" setting could not change anything. That row makes one item per seed and
was structurally capped at ten items (five liked/history/backend seeds plus at most five download seeds),
while the setting's clamp floor is ten - so `take(dailyDiscoverSize)` was a no-op for every admissible
value, contradicting the spec and README. The seed pool now scales with the setting
(`seedBudget = maxOf(5, dailyDiscoverSize / 2)`).

**P2:** (1) a covers top-up still running from an earlier load could overwrite a newer row - the top-up now
captures a load generation and publishes only when its generation is still current and the scope is active,
and `load()` bumps the generation; (2) `DownloadedIdsTest` still labelled Media3 state 1 as "failed" (it is
`STATE_STOPPED`; failed is 4) - corrected, with a `"failed" to 4` entry; (3) nothing verified the restated
Media3 number - a new test asserts `Download.STATE_COMPLETED == RecommendationFilter.STATE_COMPLETED`
against real Media3 in CI (the local harness uses a stub for that one class); (4) the seeded covers searches
dropped the PODCAST filter its fallback sibling keeps - applied there too; (5) the Media3 index read is now
wrapped in `runCatching` with a log, as the spec promised; (6) the settings dialog names the section it
edits, the unused `remember` import is gone, and the spec's Daily Discover seeding description, "stepper
rows" wording, generic-search claim and this plan's file map were corrected.

Recorded as report-only: innertube's `runCatching` swallows `CancellationException` one layer above the
documented cancellation handling, so a cancelled scope's `awaitAll` returns empty pages rather than aborting
(upstream pattern, not introduced here); the guard added to the top-up publish keeps that from writing after
the view model is gone. The suite deliberately keeps using a stale cache when the network is down, so only a
CI run proves current upstream drift.

## Code review round 3 (2026-09-26)

Reviewer A: BLOCK - 1 P0, 1 P1, 3 P2. Reviewer B: OK with notes - 3 P2. Six unique issues, all fixed:

**P0 (introduced by the round-2 fix):** a bare `isActive` in the covers top-up needed
`import kotlinx.coroutines.isActive`, which the file did not have - a compile breaker that the local syntax-only
check could not see, because it greps for `expecting`/`unexpected token` and discards `unresolved reference`.
The import is added, and the local check now runs `kotlinc` with the coroutines jar and diffs the unresolved
names against a saved baseline, so a missing coroutines import cannot pass again. Android/Hilt/DataStore names
stay unresolvable here: CI's compile remains the authority for those.

**P1 (round-2 fix incomplete):** one item per seed meant `seedBudget = maxOf(5, size / 2)` bounded the row at
`size / 2 + 5` items, so the setting still could not reach its own value. The budget is now the configured
size, and the setting's hint text says that higher counts cost more lookups per refresh. Consequence, recorded
rather than hidden: at the 200 maximum this row issues up to 200 lookups per refresh, upstream issues 5, and
the innertube client has no limiter, so throttling shows up as a silently shorter row.

**P2:** the generation guard read `loadGeneration` inside the launched coroutine, so a top-up starting after a
newer load adopted that newer generation - the value is now passed down from `load()` and the field is
`@Volatile`; five doc contradictions were corrected (the spec's Daily Discover seed description and its
`DownloadedIds` mechanism, this plan's Kover line count and missing `DownloadRecovery.kt` row, and its stale
"PODCAST filter was left alone" note), along with the Kover comment the patch extends, which now names patch
02's classes. Reviewer B's third note is accepted as a residual: under the local harness the Media3
cross-check test compares a hand-written stub with itself, so only CI's real Media3 makes it meaningful.

## Code review round 4 (2026-09-26)

Reviewer A: BLOCK - 1 P1, 6 P2. Reviewer B: OK - 3 P2. Ten unique issues, all fixed:

**P1:** the round-3 fix made the Daily Discover seed budget equal the setting, so row items equalled network
lookups - 10x upstream at the default 50 and 40x at the maximum 200 - on the same InnerTube client that
resolves playback metadata, with `withRetry` tripling failures and no limiter in the module, and `load()` (and
therefore pull-to-refresh) waiting for the whole burst. The fix decouples items from lookups: the played-seed budget
is capped at 30 (`DAILY_DISCOVER_SEED_LOOKUPS`, with up to five downloaded seeds added on top = 35 lookups)
and each seed contributes up to
`ceil(size / seedBudget)` items from its already-fetched panel, so the row still reaches its configured size
with at most 30 lookups.

**P2:** the settings hint was rendered for all three rows but only Daily Discover scales its lookups with the
size - it now reads "Higher counts can mean more network lookups"; `sectionSize`'s `runCatching` swallowed
`CancellationException` around a suspending read - it rethrows; the shelf publish carried an unreachable
`?: HomePage.Section(...)` branch (the items come from `cnrSection` and filtering never adds any) - replaced by
an explicit null check; the album-membership lookups are now capped at `MAX_COLLECTION_CHECKS` (8) per row, so
a refresh cannot issue one query per album card; `DownloadedIds.snapshots` had no caller outside its own file
and is inlined; and the spec's two cost claims, its `DownloadedIds` mechanism description and its New-files
table were corrected, with a README limitation row for the Daily Discover lookup cost and a note that a size
change applies on the next refresh. Reviewer B's note about the plan's `et --hard 33c82f9` deletion is
handled by staging that removal separately from the patch change.

## Code review round 5 (final round, 2026-09-26)

Reviewer A: OK with notes - 5 P2. Reviewer B: OK with notes - 4 P2 + a P3 nit. **No P0/P1.** Six unique
issues, all fixed in this round:

- The immediate shelf publish in the Covers & Remixes row is now generation-guarded like the top-up it feeds,
  so a late result from an older load cannot overwrite a newer row with a shorter stale shelf.
- `pad` no longer counts items the row never renders: both halves of the covers row are filtered to
  `SongItem` (which is all `HomeScreen` shows), so the row reaches the configured size.
- `keepSuggestibleAlbums` applies `MAX_COLLECTION_CHECKS` and the thumbnail filter runs before the checks, so
  the Keep Listening row cannot spend queries on cards it drops and cannot grow query counts if upstream
  raises its album limit.
- The lookup bound is restated everywhere as up to 35 (30 played seeds plus five downloaded ones), the
  "fetching stops as soon as a section reaches its target" sentence is corrected (fetches are bounded per
  seed and the row is capped, not stopped early), the cost list now includes the Quick Picks download-seed
  lookups, the `LocalRecommendationPrefs` row no longer claims to hold the defaults, and the album-check cap
  (first eight cards per row) is disclosed in both the spec and the README. The README's Daily Discover
  limitation row was retitled so it matches its own text.

Residuals recorded, not fixed: the CI-only checks (Android compile, real-Media3 cross-check, Kover gate) are
unverifiable on this machine; the `init` load versus pull-to-refresh overlap leaves the pre-existing
last-writer-wins behaviour for Quick Picks, Daily Discover and Similar Recommendations (this patch narrows the
window and guards its own row); the 200-card Daily Discover row's carousel virtualisation was not verified;
and the local Media3 cross-check test compares a hand-written stub with itself by construction.
