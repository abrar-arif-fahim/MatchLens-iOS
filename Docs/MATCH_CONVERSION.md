# In-memory fixture conversion — Step 28F.5.7

`Backend/convert_api_football_fixture.py` is a reusable function module, not a
retrieval/import script. It does not read files or credentials, call APIs, print
fixtures, write output datasets, or connect to Firebase. Existing preview and
schema scripts are preserved. Only standard libraries and the existing local
schema validator are used.

## Calling the converter

From another backend script (after independently verifying input provenance):

```python
from convert_api_football_fixture import ReviewRequired, convert_fixture

# Only already verified associations may enter this dictionary. These two were
# explicitly confirmed for our existing Barcelona/Real Madrid preview.
verified_teams = {529: "wikidata_Q7156", 541: "wikidata_Q8682"}

# provider_fixture is ONE fixture object from response[], not the API envelope.
try:
    match = convert_fixture(provider_fixture, verified_teams, is_demo=False)
except ReviewRequired as error:
    print(error)  # Our own readable explanation; no raw provider response.
```

The existing preview's local `load_team_mapping()` result can also supply this
dictionary by taking each entry's `teamId`. No live lookup or mapping discovery is
performed by the converter. The caller is responsible for supplying verified
associations, not arbitrary guesses; structural validation cannot prove identity
verification occurred. Unknown team IDs, duplicate club associations or malformed
mapping entries require review. Provider country/name similarity never substitutes
for a missing mapping. This step does not create a complete five-club mapping
registry or assume unstored IDs for other clubs.

## Conversion rules

- Required: fixture object, positive integer fixture ID, supported status code,
  home/away team IDs present in the verified mapping, provider competition ID,
  nonempty competition name and integer season. Boolean/string IDs are rejected.
- Real-source IDs use `match_api_football_fixture_<provider_id>`. The provider
  namespace and its unique fixture ID make repeated conversions deterministic;
  changes to kickoff, status, team order or scores do not regenerate the ID.
  Another fixture ID yields another internal ID. `sourceMatchId` stores the
  provider ID separately as a string. Reserve this namespace for this converter;
  any older manually assigned match IDs would need a reviewed alias/migration.
- Team IDs become existing `wikidata_Q...` document IDs. No remote existence
  check occurs. These remain plain IDs, following the existing schema convention.
- Offset-aware ISO kickoff or integer Unix timestamp becomes UTC
  `YYYY-MM-DDTHH:MM:SSZ`. If both exist, they must agree. Missing time is allowed
  only for postponed/cancelled records. Naive, contradictory, invalid or
  subsecond instants are rejected rather than guessed or truncated.
- `NS` becomes scheduled; `1H/HT/2H/ET/BT/P/LIVE` become live; `FT/AET/PEN` become
  finished with respectively regularTime/extraTime/penalties; `PST` becomes
  postponed; `CANC` becomes cancelled. Live records have no finishType yet.
- Final/current goals are copied from `goals.home/away`. Regular time comes from
  `score.fulltime`, extra-time-period goals from `score.extratime`, and shootout
  tallies from `score.penalty`. No totals are added, scores subtracted or missing
  values filled with zero. Cumulative/contradictory extra-time values fail schema
  consistency checks; they are not automatically reinterpreted.
- Missing/explicit-null goal or period pairs stay unknown (`None`, hence JSON
  null if a future approved step serializes them). A known home value with an
  unknown away value cannot be represented by the current paired-score contract:
  it requires review. Finished totals cannot be derived from other score fields.
- Season becomes its string representation. Provider competition ID becomes
  `sourceCompetitionId`; `competitionId` stays null in the legacy call. Passing
  `competition_catalog=load_verified_catalog()` enables strict reviewed lookup.
  Unknown/pending/conflicting associations require review instead of remaining
  silently unresolved. Competition name is copied, not invented; IDs are never
  guessed from a name or season token.
- The final dictionary is checked by `validate_match()` and contains exactly the
  existing 21 fields. Incompatible data raises `ReviewRequired`, whose message
  begins `REVIEW REQUIRED:`. No partial output record is returned or input mutated.
- Referee, venue, images, raw provider objects, events, lineups, statistics and
  arbitrary extra fields are not copied. Future records can reference `matchId`.

## Provenance and tests

Every call must explicitly pass `is_demo=True` for fictional data or
`is_demo=False` for real-source records. The converter cannot verify a real match
occurred merely by inspecting its shape. Real-source mode uses source
API-Football and isDemo false; conversion is not licensing or redistribution
clearance. Provider permissions still require review before storing/publishing.

Demo mode uses `demo_api_football_fixture_<synthetic_id>`, source demo, isDemo true,
and null source fixture/competition IDs, as required by the current demo schema.
The synthetic numeric input ID only provides stable correlation within the demo
namespace; it is not presented as an actual provider ID. An input explicitly
marked `isDemo: true` cannot be converted using real-source mode.

Run all current local tests from the repository root:

```powershell
python -B -m unittest discover -s Backend -p "test_*.py" -v
```

The new test module builds fictional API-style records in memory. It covers
regular/extra-time/shootout finishes, scheduled/live/postponed/cancelled states,
unknown mappings, unsupported statuses, missing required data, UTC conversion,
score consistency, immutable inputs and stable IDs. A synthetic in-memory-only
test exercises the real-source metadata branch; it is never saved as real data.

## Limits of this step

Suspended, interrupted, abandoned, awarded, walkover and time-to-be-defined states
still need explicit schema decisions. Aggregate scores, halftime detail and
competition/tie rules are not added to the match schema. Missing period totals
are not proof a period was unplayed. Mapping verification, real-world accuracy,
provider permissions and future database conflict checks remain outside this pure
conversion function. No API request, provider dataset or import is added.

Stop after Step 28F.5.7.

## Integrated backend batch — local mappings and read-only services

The user's current batch instruction supersedes the historical stop points.
`Markdown.md` defines Phases A–H and references 28F.5.1; neither it nor the other
repository documents defines a complete numbered Phase 28 or any Phase 29 scope.
The confirmed match-workflow goals and the user's explicit competition/integration
requirements guide this batch. They cannot establish completion of unspecified
Phase 29 requirements.

Already implemented and preserved: player/team Wikidata workflows, safe existing
importers, ADC setup, match and competition schemas, UTC/period-score conversion,
season inspection, and manual API previews. The baseline actually had 128 passing
tests, rather than the older 109-test checkpoint in the request.

Added components:

- `competition_mapping.py` and `input/competition_mappings.json`: stable manual
  reference IDs and strict lookup of the four user-confirmed competition bindings.
- Optional `competition_catalog` in `convert_fixture()`: resolves internal IDs
  while preserving provider IDs and the current 21-field match schema. Demo
  conversion never takes a real competition association from a provider number.
- `match_service.py`: `prepare_fixture()` joins conversion to local reference
  validation; `prepare_matches()` validates every record before a preview starts.
  Returned items contain `match`, `firestoreData`, `homeTeam`, `awayTeam`,
  `competition`, and `competitionSeasons`. Firestore preparation uses a UTC
  datetime for kickoff, reusing the existing preview helper. Edition records are
  available separately; no edition is chosen from a provider season token.
- `preview_matches()` produces CREATE/UPDATE/NO CHANGE plans. It checks team
  document IDs/Wikidata IDs and the competition document against the reviewed
  local identity, then reuses the existing typed match comparator. Missing or
  conflicting references stop the complete plan. Distinct references are cached
  only within one preview. This is a read-only plan, not an atomic snapshot or
  permission to write it later.
- `local_document_reader()` provides isolated local snapshots.
  `firestore_document_reader(db)` wraps an explicitly configured existing client
  and permits point reads only from teams, competitions and matches. It selects
  managed fields, disables automatic read retries, sanitizes SDK failures, and
  neither initializes Firebase nor queues writes.
- `preview_backend_pipeline.py` runs the existing fictional match through those
  services using local snapshots. It has no live mode, output option or apply flag.

Team-record validation is shared with the existing team preview; team-reference
identity validation is shared with the existing Firestore reference checker.
No schema/version migration, new dependency or frontend change was necessary.

Local checks, safe to run without network or credentials:

```powershell
python -B Backend/competition_mapping.py
python -B Backend/preview_backend_pipeline.py
python -B -m unittest discover -s Backend -p "test_*.py" -q
```

The offline demo reports a **simulated CREATE 1**, using empty local match
snapshots. It does not assert that the real database lacks that document.

From another Python component, with caller-supplied input already in memory:

```python
from competition_mapping import load_verified_catalog
from match_service import prepare_fixture, preview_matches, firestore_document_reader

catalog = load_verified_catalog()
item = prepare_fixture(provider_fixture, verified_teams, prepared_teams, catalog,
                       is_demo=False)
# item stays in memory. This is not approval to save or redistribute it.
# Only an explicit caller with a configured db may perform the following reads:
plan = preview_matches([item["match"]], prepared_teams, catalog,
                       firestore_document_reader(db))
```

A fictional fixture instead requires `is_demo=True` plus an explicit
`demo_competition_id` and the fictional competition catalog. Malformed demo
markers cannot be silently processed as real-source records. Unknown provider
teams/competitions and unsupported statuses still require review.

The existing live conversion preview can use a catalog on a **manual** run:

```powershell
python -B Backend/preview_api_football_conversion.py --competition-catalog Backend/input/competition_mappings.json
```

That command makes its existing single API request when the user runs it. It was
not executed for this batch. Its no-flag behavior and one-request limit remain
compatible with earlier tests; no fallback or persistent response storage is added.

Results after final review: **168 tests passed, zero failed** (baseline 128;
Batch A 146; Batch B 165; final review 168). New tests use fictional fixture
results in memory and isolated readers/SDK mocks, covering mappings, seasons,
period scores, provenance, duplicate inputs, missing/inconsistent references,
immutable preparation, typed comparisons, read caching and error handling.

**Phase 28: PARTIALLY COMPLETE.** The specified mapping and offline integration
work is implemented; a complete numbered phase definition is unavailable, and
approved real-data persistence, competition/match database provisioning and
live verification have not been performed under the current restrictions.

**Phase 29: BLOCKED.** Its original requirements are absent. The reusable service
and integration-test work requested in this batch is delivered, but cannot be
certified as an undocumented phase. Provider-to-internal season association,
events/lineups/statistics, authentication and user data are not newly invented
as Phase 29 requirements.

No live API requests, database changes, Firebase rule changes, frontend edits,
credential or Firebase configuration changes, commits, pushes or merges were performed.
The existing environment still emits Google-library warnings about Python 3.10.11;
the warnings did not fail these tests. Live read permissions and provider storage/
redistribution rights remain matters for explicit review.

## Final backend review

The subsequent review read `Markdown.md` completely and compared the actual
code and tests with the documented match workflow. Phase 28 remains **PARTIALLY
COMPLETE**; Phase 29 remains **BLOCKED** because no original numbered definition
is present. The existing generic service functions cannot establish completion
of an undefined phase.

Three integration tests were added to `test_match_service.py`, with no production
feature changes. They read fictional API-shaped fixture JSON from memory, use
all four reviewed competition bindings across seven match states, independently
validate the final 21-field record, and exercise CREATE, UPDATE and NO CHANGE
against isolated snapshots. Separate tests keep explicit demo provenance intact
and cover all three operations through a mocked Firestore adapter, including
managed-field selection and assertions that no writes, batches or transactions
occur. Synthetic fixtures exercise real-source metadata only in memory; they are
never stored or presented as actual historical results.

Final execution: **171 tests passed, zero failures**, up from the 168-test review
baseline. Both local commands also passed. Five player IDs, five team IDs, the
four competition references and the demo schemas were validated locally with
network access and live client creation blocked.

Still missing or unverified: the full numbered phase requirements, approved
real competition/match imports and live read-back verification, provider-season
associations, and player-linked match events/lineups. The current match schema
links teams and a competition; it does not implement those player relationships.
No external requests, provider-data files, database changes, frontend edits or
Git commits/pushes were made during this review. Python 3.10 support warnings
remain an environment issue and did not fail the tests.
