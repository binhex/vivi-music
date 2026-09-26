# Recommendations: hide already-downloaded items and make section sizes configurable

Date: 2026-09-26
Status: approved (design), pending implementation
Patch: `local-patches/02-recommendations.patch` (new; `01-download-folder.patch` stays as it is)

## Problem

Three home-screen sections suggest music without regard for what the user already owns, and they are
capped at small fixed sizes:

- **Quick Picks** (`HomeViewModel.getQuickPicks`) builds related songs from listening events in the last
  two weeks and caps the row at `.take(20)`.
- **Daily Discover** is seeded from the ten most-played artists and five most-played songs, then filled
  by similar/related lookups.
- **Covers & Remixes** is a remote YouTube Music shelf located by title (contains "cover" and "remix"),
  so its item count is chosen by the server; a generic "music covers and remixes" search is used only
  when that shelf is missing, and it too caps at 20.

Nothing consults the download index, so downloaded material reappears, and the row sizes cannot be
changed without editing upstream code.

## Goal

1. Suggestions must be related to what the user has downloaded as well as to what they have played.
2. Anything already downloaded must not be suggested again.
3. Quick Picks, Daily Discover and Covers & Remixes must show far more items, each with its own
   configurable count defaulting to 50.
4. All of it ships as a patch, so upstream releases keep applying and merging cleanly.

## Decisions (agreed with the user)

| Question | Decision |
| --- | --- |
| What makes suggestions "related to downloads" | Existing play-history seeds are kept, and downloaded songs are added as extra seeds |
| Where the size settings live | `Settings > Content > Recommendations`, one hook line in upstream `ContentSettings.kt` |
| Covers & Remixes, whose size the server decides | Keep the remote shelf as the head of the row, then pad locally until the configured count |
| One shared count or one per section | Three independent counts, each defaulting to 50 |
| Which rows hide downloaded items | The three named sections plus Similar Recommendations, Keep Listening and Forgotten Favorites (sizes unchanged for those three) |

## Architecture

All new logic is fork-owned. Upstream files receive short, stable hooks only.

### New files

| File | Responsibility |
| --- | --- |
| `app/src/main/kotlin/com/music/vivi/playback/RecommendationFilter.kt` | Pure Kotlin, no Android types: exclusion, collection rule, sizing, seed selection, padding order |
| `app/src/main/kotlin/com/music/vivi/playback/DownloadedIds.kt` | Reads Media3's download index once per refresh and returns the completed download ids |
| `app/src/main/kotlin/com/music/vivi/playback/LocalRecommendationPrefs.kt` | DataStore keys and defaults for the three sizes |
| `app/src/main/kotlin/com/music/vivi/ui/screens/settings/LocalRecommendationSettings.kt` | The settings group (three stepper rows) |
| `app/src/main/res/values/local_recommendation_strings.xml` | Strings for that group |
| `app/src/test/kotlin/com/music/vivi/playback/RecommendationFilterTest.kt` | Pure unit tests for the filter core |

### Pure API (`RecommendationFilter`)

| Function | Behaviour |
| --- | --- |
| `keepUndownloaded(items, downloadedIds, idOf)` | Drop items whose id is in `downloadedIds`, preserving order |
| `keepCollection(trackIds, downloadedIds)` | Return false only when `trackIds` is non-empty and every id is downloaded; keep when membership is unknown |
| `resize(items, size)` | Take at most `size` items, preserving order |
| `clampSize(value)` | Clamp a configured size into 10..200 inclusive |
| `seedIds(playedSeeds, downloadedSongs, max)` | Return the played seeds unchanged, then append downloaded songs not already present, capped at `max` |
| `pad(remote, local, size, downloadedIds, idOf)` | Remote items first, then local items, both filtered, de-duplicated by id, capped at `size` |

`DownloadedIds` is the single Android-coupled piece. It reads
`DownloadUtil`'s `downloadManager.downloadIndex`, keeps entries in the `COMPLETED` state, and returns
their ids. Downloads are keyed by `song.id` / `mediaMetadata.id` (the YouTube video id), which is also
the id of the items in every affected section, so one id set filters both local and remote material.

## Data flow

Each home refresh does the following once, then reuses the results:

1. Read the three configured sizes (`LocalRecommendationPrefs`), clamped to 10..200.
2. Read the completed download ids into a `Set<String>` (`DownloadedIds`).
3. **Quick Picks**: gather last-two-week candidates and the existing related lookups, filter with
   `keepUndownloaded`, and fill toward `quickPicksSize`. The existing last-song-listened mode is
   filtered identically.
4. **Daily Discover**: keep the existing most-played artist and song seeds, then add downloaded songs as
   extra seeds via the existing `getSongsByIds` query (`seedIds`, at most five extra seeds). Filter the
   results and fill toward `dailyDiscoverSize`.
5. **Covers & Remixes**: take the remote shelf, filter it, then run seeded "cover" and "remix" searches
   for up to three seeds (downloaded first, then most-played) and pad toward `coversAndRemixesSize`. The
   existing generic "music covers and remixes" search is used only when there are no seeds at all, and
   it is filtered and padded like any other local source.
6. **Similar Recommendations, Keep Listening, Forgotten Favorites**: filter every list, keep the
   upstream sizes.
7. A section whose filtered list ends up empty is not rendered.

Fetching stops as soon as a section reaches its target or its sources are exhausted. Each source is
queried at most once per refresh, so the larger counts never turn into unbounded pagination.

## Behaviour and edge cases

- Only downloads in the `COMPLETED` state count as downloaded. Queued, partial and failed downloads are
  not hidden.
- Individual items are always filtered. Album and playlist cards are dropped only when every one of
  their tracks is already downloaded, verified through the existing `albumSongs(albumId)` query.
  A collection whose membership cannot be determined is kept, never hidden.
- A section that cannot reach its target shows everything it has. It is never padded with
  already-downloaded items.
- Changing a size takes effect on the next home refresh; no restart is required.
- No new permissions and no new network endpoints; the extra cost is one download-index read per
  refresh plus the bounded seed searches for the covers row.

## Settings surface

`Settings > Content > Recommendations` contains three rows, each a stepper from 10 to 200 in steps of 10,
defaulting to 50:

| Setting | Preference key | Default | Range |
| --- | --- | --- | --- |
| Quick Picks items | `localRecommendation.quickPicksSize` | 50 | 10..200 |
| Daily Discover items | `localRecommendation.dailyDiscoverSize` | 50 | 10..200 |
| Covers & Remixes items | `localRecommendation.coversAndRemixesSize` | 50 | 10..200 |

The row UI, strings and preference keys are fork-owned. Upstream `ContentSettings.kt` gains exactly one
line that calls the fork-owned settings group.

## Upstream contact (complete list)

| File | Change | Size |
| --- | --- | --- |
| `app/src/main/kotlin/com/music/vivi/viewmodels/HomeViewModel.kt` | Read the three sizes and the downloaded ids; filter the six rows; add downloaded seeds; pad the covers row; replace the three hardcoded caps for the named sections with the configured sizes | roughly 10-20 lines |
| `app/src/main/kotlin/com/music/vivi/ui/screens/settings/ContentSettings.kt` | One call to the fork-owned settings group | 1 line |

No other upstream file is modified. `HomeScreen.kt` is untouched: it already assembles its section list
only for sections that have items (`quickPicks?.isNotEmpty() == true`, `coversAndRemixes?.items?.isNotEmpty() == true`
and the equivalents for Daily Discover, Keep Listening and Forgotten Favorites), so a section that
filters down to nothing simply does not render.

## Error handling

- Media3 download-index read fails: treat the downloaded set as empty, log it, and continue. Filtering is
  disabled rather than the app hiding everything.
- DataStore read fails: fall back to the default sizes of 50.
- Network failure: existing behaviour is preserved. The database-backed parts of Quick Picks and Daily
  Discover still populate, and the covers row simply stays at whatever the remote shelf returned.
- Invalid or out-of-range stored size: clamp to 10..200.

## Testing

Pure unit tests in `RecommendationFilterTest` cover exclusion by id, the collection rule (fully owned,
partially owned, unknown membership), size clamping, padding order and de-duplication, and downloaded
seeds not duplicating played seeds. The existing CI gates (unit tests, Kover coverage, lint, the Local
Patch Build, and the weekly upstream drift canary) cover the rest.

The six `HomeViewModel` hooks are not unit-tested because that class is Android-coupled. They are kept to
single calls into tested code and live at stable call sites, which is the honest limit of what this
design verifies locally.

## Non-goals

- No filtering of the remote generic YouTube home shelves, the community section, or moods and genres.
- No per-section enable or disable switch.
- No change to the recommendation algorithms themselves.
- No redesign of the rows, which already render lists of any length.

## Risks

- Upstream may restructure `HomeViewModel`'s section builders. If it does, `02-recommendations.patch`
  fails to apply loudly in `Local Patch Build` and the weekly drift canary rather than silently building
  the wrong thing.
- The covers row depends on seeded search results; YouTube may return fewer matches than requested, in
  which case the row is shorter than the configured count by design.
