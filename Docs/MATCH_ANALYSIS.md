# Offline match events and highlights

This batch follows **Phase E — Build the Match Pipeline** and **Phase F — Add
Highlights and Analysis** in `Markdown.md`. That roadmap does not define Phases
30/31 or a complete numbered Phase 29. These additions implement the safe backend
parts of E/F; they do not establish completion of the whole app roadmap.

## Current status

| Scope | Status | Evidence / remaining work |
| --- | --- | --- |
| Previous Phase 28 | PARTIALLY COMPLETE | Four reviewed competition mappings and the validated offline fixture pipeline exist. Approved real competition/match persistence and live read-back remain pending. |
| Previous Phase 29 | BLOCKED | Its original numbered requirements are absent; no requirements are inferred from test counts. |
| Phase E | PARTIALLY COMPLETE | Match conversion, competition/team references and previews already existed. Curated event preparation and player identity links are now implemented. Approved match/event imports remain pending. |
| Phase F | PARTIALLY COMPLETE | Highlight metadata, event markers, timelines and seek arguments are implemented offline. Licensed media, actual playback and SwiftUI navigation remain pending. |

Baseline: 171 tests passed on `main` at `2b20b22`. After the Phase E additions,
192 passed. After Phase F and final review, **223 tests passed with final result
OK**. The complete suite and the offline analysis command were actually executed.
Google libraries still warn about this environment's Python 3.10.11 support.

## Reused pipeline

`match_service.prepare_fixture` and `prepare_matches` remain the match/competition/
team entry points. `match_event_service.prepare_event_bundles` extends these read
bundles with events and public player identities. Player validation is shared with
`import_multiple_players.validate_player_records`; the existing importer still
accepts at most five players. The read service can validate a larger prepared list
without expanding any upload functionality.

`highlight_service.prepare_highlight_bundles` adds highlights and derived
`highlightTimelines`. All input records and references must pass before a complete
bundle is returned. Caller data is not mutated. Neither service reads files,
initializes Firebase, accesses media nor makes requests. Importing the modules has
no external side effects.

Events/highlights are separate records linked by `matchId`; they are **not** fields
added to the existing 21-field match schema. A future storage layout could use
`matchEvents/{eventId}` and `highlights/{highlightId}` queried by `matchId`. These
collections, queries and indexes have not been created. Derived read bundles must
not be uploaded as growing arrays inside a match document.

## Curated event fields

Every record contains exactly these fields:

| Field | Meaning |
| --- | --- |
| `eventId` | Stable child ID generated with `make_related_id(matchId, "event", stable_key)`. |
| `matchId` | Parent match ID present in the validated batch. |
| `teamId` | Participating home/away team ID; nullable only for an `other` event with no player. |
| `playerId` | Existing validated `wikidata_Q...` player document ID, or null. A player also requires a participating team. |
| `eventType` | `goal`, `yellowCard`, `redCard`, `save`, `substitution` or `other`. |
| `matchMinute` | Nonnegative whole football minute, or null when unknown. |
| `addedTime` | Nonnegative whole added-time minutes, or null; requires a known base minute. |
| `label` | Nonempty public display text. |
| `isDemo` | Boolean matching the parent match. |
| `source` | `demo` for fictional records; `manual` for separately curated real-source records. |

Example IDs: `demo_event_regular_001__goal_1` for `demo_regular_001`, or
`event_api_football_fixture_123__goal_1` for `match_api_football_fixture_123`.
The double underscore unambiguously separates the parent slug and stable child
key. A caller must keep its child keys stable; IDs are not derived from mutable
labels, clocks or list order. No provider event-ID mapping is assumed.

Only live or finished matches can have occurred events. Unknown players and
unknown clocks stay null. Displayed football clocks retain added time (`45+2`);
45+10 sorts before minute 46. A player reference verifies an identity, **not roster
membership or the truth of an event**. No roster/lineup relationship is invented.
Event lists may be incomplete and never recalculate scores or period totals.

## Highlight fields and navigation

Every highlight contains exactly these eleven fields:

| Field | Meaning |
| --- | --- |
| `highlightId` | Stable match-scoped ID generated with kind `highlight`. |
| `matchId` | Validated parent match ID. |
| `title` | Nonempty public display text. |
| `mediaType` | `bundle` or `https` for an authorized reference; otherwise null. |
| `mediaReference` | Simple `.mp4`/`.mov`/`.m4v` bundle resource filename, or HTTPS reference; otherwise null. |
| `durationSeconds` | Supplied positive finite duration, or null. Never derived from football minutes. |
| `rightsStatus` | `unconfirmed` or `authorized`. |
| `rightsEvidence` | Public note recording the caller's rights review, required for authorized references; otherwise null. Never private contracts or credentials. |
| `markers` | Array of `{ "eventId": ..., "videoSeconds": ... }`. |
| `isDemo`, `source` | Same provenance rules as curated events. |

Unconfirmed media must have null type, reference and rights evidence. HTTPS
references cannot contain user/password credentials, query parameters or fragments;
bundle references cannot contain local paths. No media is opened or downloaded.
`authorized` is a caller-supplied review claim, **not independent licence
verification**. Any actual use still needs confirmed permission and media availability.

Markers reference validated events from the same match. Their times must be
finite numbers between zero and the supplied duration, including the endpoint.
Booleans, negative/nonfinite numbers, unknown durations with markers and duplicate
event markers within a highlight are rejected. An event may occur in several
different highlight clips. Empty marker arrays and null durations are preserved.

Derived timelines sort by clip seconds and carry event/team/player references,
labels and the nullable football clock. The two clocks are independent: no
conversion from a match minute to a video timestamp is attempted.
`playbackEligible` only reflects supplied authorized metadata. `playback_target`
returns media reference and seek seconds for a selected marked event in a validated
bundle, or raises a clear error; it never plays a video or guesses a position.

`preview_curated_records` compares validated records against local dictionaries
using only managed fields. CREATE/UPDATE/NO CHANGE plans preserve unrelated fields,
and comparison is type-strict inside nested marker lists. There are no writes.

## Run locally

From the repository root in PowerShell:

```powershell
python -B Backend/preview_match_analysis.py
python -B -m unittest discover -s Backend -p "test_*.py" -q
```

The command reuses the existing fictional regular-finish schema case, local CC0
player/team references and fictional competition. It constructs two explicitly
fictional events and one virtual timeline in memory, with null media references
and unconfirmed rights. Player participation and marker positions are fictional.
It exercises all three simulated operations for one match, two events and one
highlight. It does not assert anything about the live Firestore database.

Tests additionally exercise fictional API-shaped fixture conversion through team,
competition, player, event and highlight preparation, including regular time,
extra time, penalties, live matches, cross-match references, nulls and invalid
types. The real-source contract is tested with synthetic in-memory records only.
Network and real Firebase client creation are blocked in the new tests. The command
has no apply, live or output-file options.

## Remaining work

- Confirm provider storage/redistribution rights before any real-data persistence.
- Review and provision approved competition/match/event data in a separately
  authorized step; this batch performs no Firestore operations.
- Add verified roster/lineup and provider-event mappings only when sourced and
  approved; neither can be inferred from the current player identities.
- Supply licensed media and explicit reviewed rights metadata; check availability
  and playback on an iPhone before claiming the full Phase F complete.
- Integrate these read bundles with SwiftUI in a later frontend batch.
- Define the original numbered Phase 29 requirements if that numbering is retained.
- Upgrade the local Python environment separately to a supported version.
