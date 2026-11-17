# MatchLens match schema — through Step 28F.5.6

This step defines and validates a local example, not an import. The example in
`Backend/input/match_schema_example.json` describes a **fictional scheduled
fixture** between FC Barcelona and Real Madrid. Its competition, season and UTC
kickoff are demonstration values. It is not a real fixture or result.

The design preserves the flat fields proposed in `Markdown.md`, adds competition
identity and season, and keeps an external match ID separate from our internal ID.

## Proposed document

Future path: `matches/{matchId}`. No collection or document is created by this step.

All 21 fields are required; unknown values use explicit nulls. Unexpected fields
are rejected rather than imported. This is still a local design/validation step.

| Field | Type | Meaning |
| --- | --- | --- |
| `matchId` | string | Stable application document ID: `demo_<slug>` for demos, `match_<slug>` for real data. |
| `homeTeamId` | string | Document ID within `teams`, such as `wikidata_Q7156`. |
| `awayTeamId` | string | Different team document ID, such as `wikidata_Q8682`. |
| `competitionId` | string or null | Verified internal competition ID: `demo_competition_<slug>` or `competition_<slug>`. Use null when a real mapping has not been verified. |
| `sourceCompetitionId` | string or null | External competition ID belonging to `source`; never silently used as the internal competition ID. Demo records require null. |
| `competition` | string | Readable competition name; a display snapshot, not its identifier. |
| `season` | string | Source-appropriate readable season, e.g. a year or season range; demo input says `Demo season`. |
| `kickoffUtc` | string or null | Exact UTC timestamp `YYYY-MM-DDTHH:MM:SSZ`; null permitted only for postponed/cancelled matches with no known kickoff. |
| `status` | string | `scheduled`, `live`, `finished`, `postponed`, or `cancelled`. |
| `finishType` | string or null | Finished only: `regularTime`, `extraTime` or `penalties`. Null for every unfinished/unplayed status. |
| `homeScore` | integer or null | Home goals known so far, or the final score. Unknown is null, not an invented zero. |
| `awayScore` | integer or null | Away goals under the same rules. |
| `regularTimeHomeScore`, `regularTimeAwayScore` | integer or null | Scores after regular time (including stoppage time), excluding extra time and shootout. |
| `extraTimeHomeScore`, `extraTimeAwayScore` | integer or null | Goals scored **during extra time only**, not cumulative scores after extra time. |
| `penaltyHomeScore`, `penaltyAwayScore` | integer or null | Shootout tally only; never added to match goals. Penalty goals scored during regular/extra time belong to ordinary goals, not this pair. |
| `isDemo` | boolean | Explicitly distinguishes a fictional record from intended real data. |
| `source` | string | Match-data source. Exactly `demo` for examples; a reviewed provider/source name for real data. |
| `sourceMatchId` | string or null | Original source's public fixture ID, stored as a string; null for demos and required for real records in this version. |

Slugs use lowercase letters/digits separated by single underscores. Team IDs use
`wikidata_Q` followed by a positive integer with no leading zero. Match IDs do not
equal team IDs or source fixture IDs. Allocate each match ID once, reuse it for
updates, and do not regenerate it when kickoff, score or status changes. A later
pipeline will need to map `(source, sourceMatchId)` to that stable internal ID to
avoid duplicates. Competition IDs are internal IDs, not assumed Wikidata IDs or
provider IDs. The external `sourceCompetitionId` can be known while the internal
`competitionId` remains null. The latter must not be guessed from a provider ID.
Neither a real competition document nor an external mapping is created here.

`source` describes the match facts, not the team identity source. Referencing
Wikidata teams does not make a fictional fixture Wikidata-sourced. Local validation
does not verify football facts, source ownership or reuse permissions.

## Score and time rules

| Status | Scores |
| --- | --- |
| `scheduled` | Both null. A match that has not started is not already 0–0. |
| `live` | Both nonnegative integers, or both null if the live score is unavailable. |
| `finished` | Both nonnegative integers, including legitimate 0–0 scores. |
| `postponed` | Both null; no official result is represented. |
| `cancelled` | Both null; no official result is represented. |

The same paired-null/nonnegative-integer rule applies to each period pair. Mixed
known/unknown pairs, negative values, floats, strings and booleans are rejected.
Scheduled/postponed/cancelled records require every score field and finishType to
be null. Live records may contain available current/period scores, but finishType
stays null because the outcome is not final. A known 0 is different from null.

`homeScore`/`awayScore` are the supplied current total or final goals, including
extra time if played, **excluding shootout tallies**. Finish type is separate from
the coarse status: provider FT/AET/PEN correspond to finished with respectively
regularTime/extraTime/penalties. A finished record without a known finish type
requires review; the validator does not assume regular time.

- A regularTime finish cannot contain extra-time or shootout values. A supplied
  regular-time pair must equal the final goals.
- An extraTime finish cannot contain shootout values. Regular-time and extra-time
  period pairs remain separate. If both periods and totals are known, the validator
  checks their arithmetic consistency **without updating or deriving any field**.
- A penalties finish may follow extra time or go directly to a shootout. Keep an
  unplayed/unknown extra-time pair null, not an invented 0–0. A known completed
  shootout tally must be decisive; an unknown tally may stay null even when the
  finish method is confirmed. No winner is invented from an unavailable tally.
- Available period goals cannot exceed the corresponding supplied match total.
  Missing period scores are allowed and never calculated by subtraction. Finished
  totals are required and are never calculated by addition.

For the supplied numerical pattern: final goals **3–2**, regular-time **2–2**,
extra-time period **1–0**, finishType **extraTime**. The stored final remains 3–2;
it must not become 4–2 by adding extra time a second time. The local test file
uses these numbers only in an explicitly fictional test fixture, with no actual
provider fixture/competition ID or captured provider response.

Suspended, interrupted, abandoned, awarded and walkover results still require an
explicit schema decision. Aggregate scores for two-leg ties are not modeled yet.
Do not require a drawn single-match result before extra time/penalties, because
aggregate rules may determine progression. The validator does not infer aggregate
scores, winners or competition rules. Other providers may report cumulative
extra-time scores: those require a reviewed adapter, not automatic relabeling.

Only UTC strings with seconds and a `Z` suffix are accepted in this JSON contract.
Timezone-free times, offsets, invalid calendar dates and leap seconds are rejected.
A future importer should convert a known kickoff to an aware UTC datetime for a
Firestore Timestamp. Do not mix timestamp strings and Timestamp values in the
eventual Firestore field. Unknown times remain null. The validator does not infer
status from the current date or claim that an old scheduled record is up to date.

## Relationships and future growth

- Home/away IDs resolve to `teams/{teamId}`. They are plain document-ID strings,
  following the existing project convention. This validator checks only their
  structure and difference, not whether documents exist.
- `competitionId` can later resolve to `competitions/{competitionId}`. This
  collection is proposed, not implemented or verified to exist.
- Future match events, lineups, statistics and highlight records can each store
  `matchId` to resolve `matches/{matchId}`. Events/lineups can also use existing
  `teamId` and `playerId` values where appropriate.
- Keep growing event, lineup, statistic and video data in separate records,
  rather than unbounded arrays embedded in each match. Their exact schemas and
  collections remain future work. No placeholder events or media URLs are added.
- A future application/query must explicitly distinguish real data from demos
  using `isDemo`. No real-data provider or importer is selected in this step.

## Run locally

From the repository root:

```powershell
python Backend/validate_match_schema.py
```

The validator uses only Python standard libraries, resolves the input relative to
its own file, and does not import any network-capable backend modules. It reads
only the example JSON, writes nothing, needs no credentials, and reports `SUCCESS`
or `FAILED` with exit code 0 or 1. It rejects malformed JSON, duplicate JSON keys,
wrong/missing fields, invalid IDs, UTC values, statuses, scores and inconsistent
demo/source markers. Passing is a local schema check, not an import approval.

## Step 28F.5.2 — Read-only team-reference check

Run manually from the repository root, using the terminal where
`GOOGLE_APPLICATION_CREDENTIALS` is configured:

```powershell
python Backend/validate_match_team_references.py
```

This script reuses the local schema validator before initializing Firebase, then
reads only `teams/{homeTeamId}` and `teams/{awayTeamId}`. Each document must exist,
its `teamId` must equal its document ID, and its `wikidataId` must equal the ID
without the `wikidata_` prefix. It displays safely formatted names when available;
a missing name does not invalidate otherwise consistent identifiers.

Only two valid references produce `SUCCESS` and exit code 0. Input, credential,
permission, network and reference errors produce a failure and exit code 1. The
script always finishes with `READ ONLY — No changes made to Firestore`. It has no
write operation, import option, collection scan or external football-data lookup.
This confirms team references at read time, not that the demonstration fixture is
real or that other match fields have been independently verified.

## Step 28F.5.3 — Read-only match import preview

Run manually from the repository root with the existing Firebase credentials
configured in the same terminal:

```powershell
python Backend/preview_match_import.py
```

The preview reuses the schema loader/validator, Firebase connection helper and
team-reference reader. Invalid local input stops before Firebase initialization.
Both teams must pass the existing document/identifier checks before the script
reads `matches/{matchId}`. Only these three documents are read; no collection scan
is performed. There is no write operation or apply option.

The input JSON remains unchanged. For comparison, its known `kickoffUtc` string
is converted in memory to an aware UTC datetime, representing the planned
Firestore Timestamp. A stored string is reported as different from a Timestamp,
even if its text describes the same instant. A postponed/cancelled null kickoff
remains null. Other values are compared with their schema types, so a boolean or
floating-point value cannot silently match an integer score.

After all reads succeed, the preview reports `CREATE`, `UPDATE` with old/proposed
values, or `NO CHANGE`. It compares only the current managed fields; unrelated existing
fields are ignored. Missing fields differ from explicit nulls. The final summary
counts one proposed operation and ends with:

```text
DRY RUN ONLY — No changes made to Firestore
```

A missing `matches` collection is treated as a missing document (`CREATE`); it is
not created. Missing/inconsistent teams, credential problems and failed reads
stop the preview with exit code 1 and no operation summary, rather than displaying
an incomplete plan. A completed preview has exit code 0. Demo data is labelled as
fictional regardless of the proposed action and remains unsuitable as a real
football fixture/result. No match is uploaded by this step.

## Step 28F.5.6 — Local score tests and compatibility

From the repository root, run only the local tests:

```powershell
python -B Backend/test_match_schema.py
```

`Backend/input/match_schema_test_cases.json` contains seven fictional cases:
regular-time finish, extra-time finish, penalties, scheduled, cancelled, live and
postponed. Every record uses source demo, isDemo true and null provider IDs.
The unittest script also exercises invalid types, inconsistent totals, nulls,
finish rules, ID separation, malformed files, and compatibility with the existing
preview helpers. It makes no API/Firebase calls or credential reads.

Existing field names, coarse statuses, UTC rules and the `validate_scores` helper
remain compatible. The eight new fields must be explicitly present; an older
13-field JSON record must be upgraded locally rather than silently guessed into
the new format. The main scheduled example has been upgraded. No deployed records
or provider responses are migrated by these tests. The Firestore preview already
imports the shared field set and works with the new flat fields without changes.
The API preview now checks compatible AET/PEN periods through the shared helper;
its request URL/options, one-request limit, credentials and read-only behavior are
preserved. A schema-level pass is still not full preparation or import approval.

Competition mappings and provider reuse permissions still require review before
real match preparation/importing. Stop after Step 28F.5.6.

## Repository/context differences noted

- `Markdown.md` lists `Backend/compare_player_data.py`, but that file is absent
  from this checkout. Existing player/team pipelines are preserved.
- Five prepared player and team records are present. Import safeguards exist;
  actual remote database contents were not rechecked for this offline step.
- The document's priority list starts with frontend work. The current explicit
  instruction takes precedence: complete this backend schema step first.
- Local schema validation, the read-only previews and period-score validation are
  implemented. Match ingestion/writes remain future work. Stop after Step 28F.5.6.
