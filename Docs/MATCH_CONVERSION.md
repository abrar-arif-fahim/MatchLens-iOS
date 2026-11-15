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
  `sourceCompetitionId`; `competitionId` stays null because no internal mapping
  has been verified. Competition name is copied, not invented.
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
