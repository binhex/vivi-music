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

## File map

**Created inside the patch (fork-owned):**

| Path | Responsibility |
| --- | --- |
| `app/src/main/kotlin/com/music/vivi/playback/RecommendationFilter.kt` | Pure rules: clamp, completed-id set, exclusion, resize, collection rule, seeds, padding |
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
| `app/build.gradle.kts` | Two lines inside patch 01's `kover { }` block, adding the new classes to the coverage allowlist |

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
        assertEquals(10, RecommendationFilter.resize(listOf("a"), 1).size)
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

Expected: `OK (4 tests)` and coverage lines for `RecommendationFilter` showing zero missed lines.

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

Expected: `OK (8 tests)`.

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
            size = 4,
            downloadedIds = emptySet(),
            idOf = { it },
        )

        assertEquals(listOf("r1", "r2", "shared", "l1"), padded)
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

Expected: `OK (14 tests)` and a `RecommendationFilterKt` line with zero missed lines.

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

Expected: `OK (16 tests)`, coverage lines for `RecommendationFilter` and `DownloadedIds`, all with zero missed lines.

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
rememberPreference(key, defaultValue)  // returns Pair<T, (T) -> Unit>
```

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
git diff app/build.gradle.kts | grep -c '^+'
```

Expected: `4`.

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
