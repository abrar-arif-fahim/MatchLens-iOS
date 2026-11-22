# Competition structure — Step 28F.5.9

This is a local schema design, not a Firestore import or provider-ID discovery.
No competition collection was found in the repository implementation. No remote
database was queried to establish whether such a collection exists.

`Backend/input/competition_schema_example.json` is a catalog with three arrays:
`competitions`, `seasons` and `providerMappings`. The arrays describe separate
future documents; do not store the whole catalog as one growing Firestore document.
The one competition and season supplied here are explicitly fictional. Their
geography/dates are null where unspecified; there are no provider mappings.

## Competition identity

Proposed path: `competitions/{competitionId}`.

| Field | Meaning |
| --- | --- |
| `competitionId` | Stable internal ID: `competition_<slug>` for real-source records, `demo_competition_<slug>` for fictional records. |
| `name` | Required public display name from the stated source. A name alone does not establish identity. |
| `competitionType` | `domesticLeague`, `nationalCup`, `internationalTournament`, `friendly`, or null if not established. |
| `country` | Readable country/football jurisdiction if verified; otherwise null. |
| `region` | Verified geographic scope, such as a continent or international scope; otherwise null. |
| `isDemo` | Boolean explicitly separating fictional and real-source records. |
| `source` | Origin of the prepared identity data. Demo records require `demo`; real-source records must identify their actual origin. |

Choose an internal ID once and preserve it when a name, sponsor, season, country
label or provider changes. Do not derive it automatically from a current name,
season, match ID or API-Football number. Internal IDs need not be Wikidata IDs:
teams already have a verified Wikidata identity, while competitions do not yet.
The competition ID format matches the existing match validator.

Country and region are independent nullable fields. A domestic competition may
have a known country; an international competition may have a known region and
no single country. Missing geography/type must remain null, not `unknown`, an empty
string or a guessed location. Names, source and internal identity are essential;
records missing those are rejected. Structural validation does not establish
real-world geography, men's/women's/youth classification or identity accuracy.
Additional identity detail may need a reviewed schema extension later.

## Season editions

Proposed path: `competitionSeasons/{seasonId}`. Keep seasons out of the competition
identity document and its ID. Each season contains exactly:

| Field | Meaning |
| --- | --- |
| `seasonId` | Stable ID: its `competitionId` followed by `_season_<slug>`. |
| `competitionId` | Reference to an identity present in the catalog. |
| `label` | Verified edition/display label; do not infer years from its wording. |
| `startYear`, `endYear` | Required four-digit integers; end must not precede start. Same-year and cross-year seasons are both supported. |
| `startDate`, `endDate` | Independently nullable YYYY-MM-DD boundaries; valid dates must agree with the supplied years and chronological order. |
| `isDemo`, `source` | Season provenance; demo marker must agree with its competition. |

The fictional example spans 2030–2031 without inventing exact opening/closing
dates. Another edition belongs in another season document, leaving competition
identity unchanged. IDs do not regenerate when display labels or dates change.
Multiple distinct editions in the same year range are possible; their season IDs
must differ. If essential year/edition information is unknown, leave `seasons`
empty until verified instead of inventing a season record. Exact dates can remain
null. Labels can contain sponsor/edition wording and are not parsed as dates.

API-Football's season value `2024` is a provider season token, not proof of a
2024–2025 edition or its dates. It must not automatically supply `endYear` or
create an internal season association. Future provider-season mapping is separate
work; this design defines competition mappings only.

## Future verified provider mappings

Proposed path: `competitionMappings/api_football_<providerCompetitionId>`.
Each mapping has exactly these fields:

- `provider`: exactly `API-Football` initially; another provider requires explicit
  support and its own namespace and identifier rules.
- `providerCompetitionId`: canonical positive integer **string**, separate from
  internal identity and compatible with match `sourceCompetitionId`.
- `competitionId`: null when pending; a known non-demo identity when verified.
- `status`: `pending` or `verified`.
- `verificationEvidence`: null when pending; a short explanation/reference to the
  identity checks when verified. Do not include credentials or provider payloads.
- `verifiedAt`: null when pending; explicit UTC `YYYY-MM-DDTHH:MM:SSZ` when verified.

Pending records cannot claim an internal target. Verified mappings require a
non-demo competition already present locally, evidence and a valid UTC timestamp.
Duplicate provider IDs, conflicting targets and multiple IDs from the same
provider pointing to one competition are rejected for manual review. No aliases,
fallbacks or automatic matches are inferred. These conservative rules can be
extended later if a genuine provider alias is independently verified.

A future human review must compare provider competition name, type, jurisdiction,
organizer, club/national-team category, gender/age category and available identity
evidence. A competition must not be confused with a season edition or a fixture.
Only after that review should the mapping be marked verified. The validator checks
the metadata's structure, not the truth of an evidence statement. Passing validation
never verifies licensing or authorizes storing/redistributing provider data.

At the original Step 28F.5.9, provider IDs **140, 143, 667 and 556 remained unmapped**
and 556's identity was unconfirmed. The fictional example remains unchanged.
The later backend batch adds a separate reviewed reference catalog described below;
the schema validator itself still does not discover or approve identities.

## Connection to matches

An existing match's nullable `competitionId` will reference
`competitions/{competitionId}` after a mapping is independently verified. Its
`source` plus `sourceCompetitionId` identify the provider reference separately.
The current `competition` name and `season` string remain unchanged. Neither is
a substitute for a verified reference, and a provider name need not equal the
internal canonical display name.

The existing fictional match uses `demo_competition_001`, which resolves to this
local fictional identity. This only checks local structure, not Firestore existence.
Its existing season string does not automatically link to the new example season.
A future explicit `competitionSeasonId` field/season mapping would require a
reviewed match-schema update. No such field, migration or automatic association is
introduced here. Legacy conversion leaves `competitionId` null unless its caller
explicitly supplies the reviewed competition catalog.

## Local validation

From the repository root:

```powershell
python -B Backend/validate_competition_schema.py
python -B -m unittest discover -s Backend -p "test_*.py" -q
```

The standard-library validator reuses the existing text, duplicate-JSON-key and
UTC validation helpers. It checks all fields and references, rejects duplicate
competition/season/mapping IDs, and reads only the example JSON. It writes nothing,
needs no credentials and makes no requests. Errors have exit code 1; a schema pass
has exit code 0. All synthetic mapping tests remain in memory only.

`Markdown.md` still describes match-schema work as unconfirmed and prioritizes
frontend work. The actual repository includes the completed match schema,
converter and previews, and the user's current backend-first instructions take
precedence. Existing working code and project context are preserved.

## Reviewed local mappings — backend batch

`Backend/input/competition_mappings.json` stores manually maintained reference
metadata based on the user's explicit confirmation of these identities:

| Provider reference | Internal MatchLens ID |
| --- | --- |
| API-Football 140 | `competition_la_liga` |
| API-Football 143 | `competition_copa_del_rey` |
| API-Football 667 | `competition_friendlies_clubs` |
| API-Football 556 | `competition_spain_super_cup` |

These internal IDs are application assignments, pinned in the catalog. They are
not Wikidata identifiers, provider IDs or season IDs, and must not regenerate
when names change. `source: manual` identifies the manually curated records;
`verificationEvidence` identifies the user's supplied ID/name/country/type review.
`verifiedAt` records acceptance of those local associations on 22 November 2026,
not an invented date for an earlier API lookup. No further identity attributes
or provider rights are asserted.

Competition types are MatchLens categories. Friendlies use `friendly`; the
provider's confirmed `World` label is represented as region, with country null.
The catalog contains no raw responses, fixture results, logos or season data.
`seasons` remains empty because provider year tokens alone do not establish
calendar boundaries or an internal edition mapping. Provider storage and reuse
rights remain unapproved; reference metadata does not grant those rights.

`competition_mapping.py` validates the whole catalog before lookup, resolves
canonical numeric/string provider IDs, and rejects unknown, pending, duplicate
or conflicting mappings. It also validates match-to-competition links and returns
independent copies of competition/season metadata. Passing structural validation
still does not independently prove the evidence's truth.

```powershell
python -B Backend/competition_mapping.py
```

The converter and integrated read-only service use this registry as described in
[match conversion](MATCH_CONVERSION.md). No competition or mapping document has
been created in Firestore by this batch.
