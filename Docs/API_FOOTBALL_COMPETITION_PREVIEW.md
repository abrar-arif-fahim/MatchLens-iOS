# Competition identity preview — Step 28F.5.10

Run manually from the repository root:

```powershell
python -B Backend/preview_api_football_competition.py --competition-id 140
```

The script reads the existing `API_FOOTBALL_KEY` using the project's `.env`
loader. With valid local arguments/credentials, it attempts one request:
`GET /leagues?id=140`. It blocks redirects, uses a 20-second timeout and makes no
retry, fallback, pagination or additional endpoint call. Missing credentials or
invalid command arguments stop before a request. Imports and automated tests do
not contact the API. Existing scripts, schema files and mappings are unchanged.

The default expectations are user-supplied provider references: ID 140, name
La Liga, country Spain, type League. These are not an internal MatchLens mapping.
The returned envelope must have valid counts, one record and complete pagination
metadata. ID must be a matching positive integer, and name/country/type must match.
Name normalization ignores case, accents, punctuation and spacing only, allowing
La Liga/LaLiga. It retains every letter and digit; different divisions, women's
or youth categories, sponsor names and other aliases are not guessed. Such
differences require manual review even when ID/country/type agree.

- `Identity: VERIFIED`: all four expected identity fields match in a unique,
  complete provider result. This is a provider-response identity check, not
  independent certification of facts, mapping creation or licensing approval.
- `REVIEW REQUIRED`: missing/mismatched identity fields, no unique result or
  incomplete pagination. Reasons are printed and no candidate is auto-selected.
- `ERROR`: credentials, HTTP/connectivity, API errors, invalid JSON or a malformed
  response envelope prevent the check. HTTP status and filtered provider error
  details are shown when available, including subscription/quota failures.

Season information is displayed separately: provider year token, supplied start
date, supplied end date and current flag. A provider year such as 2024 never
automatically becomes an end date/year. Missing dates stay null. Invalid dates,
reversed boundaries, unavailable dates, duplicate provider years and invalid
flags are labelled `Season REVIEW REQUIRED`; they do not rewrite the competition
identity verdict. Missing seasons are reported as unavailable and require season
metadata review. No internal season
ID or association is inferred, and coverage flags do not trigger more requests.

Exit code 0 means identity passed with no season-data issues; 1 means
identity/season review or an API/configuration error.
Invalid CLI arguments exit 2 before reading credentials or requesting data.

For future individually reviewed IDs, supply all expected identity values in one
invocation: `--competition-id <id> --expected-name "<name>" --expected-country
"<country>" --expected-type League` (or `Cup`). No other preset or list of IDs is
checked automatically. This step does not verify 143, 667 or 556.

Only selected identity fields, season metadata, fixed messages and filtered API
errors are printed. Raw payloads, logos, account data, coverage objects and request
headers are not displayed. Provider data stays in memory; no JSON files, logs,
Firebase documents or internal mappings are written. Do not redirect output to a
dataset/log as part of this step. Provider permissions must be reviewed before
future storage or redistribution.

Offline tests use fictional HTTP responses and mock credentials/network access:

```powershell
python -B -m unittest discover -s Backend -p "test_*.py" -q
```

Stop after Step 28F.5.10. Identity approval, internal mapping and import decisions
remain separate work. No live request is run automatically during development.

## Step 28F.5.10.3 — Inspect Friendlies Clubs

Only ID 667 and the expected name Friendlies Clubs are established for this step.
The existing script now accepts optional `--inspect`, allowing unknown expected
country/type values to stay null. It never fills these from an API response or
the La Liga defaults. Run manually from the repository root:

```powershell
python -B Backend/preview_api_football_competition.py --competition-id 667 --expected-name "Friendlies Clubs" --inspect
```

This makes one `GET /leagues?id=667` request with the existing request/error/quota
handling, without retries or additional lookups. It compares the known ID/name,
displays the returned country/type as inspection data, and keeps seasons separate.
The result is `Identity: REVIEW REQUIRED`, with country and competition type
listed as needing independent confirmation. No internal ID or mapping is created.
Null country/type values in the expected identity mean unconfirmed expectations,
not a claim that the actual competition has no country or category.

After independent review, explicit `--expected-country` and `--expected-type`
arguments can be supplied in a later run. Only when all expectations are supplied
and match a unique complete provider result can identity be `VERIFIED`.
Normal verification mode still requires all expectations (or its existing La Liga
defaults); La Liga and the explicit Copa del Rey command are unchanged.

No provider country/type is hardcoded for 667. Tests use synthetic metadata only.
Stop after Step 28F.5.10.3; provider-data storage and mapping remain separate steps.

## Step 28F.5.10.4 — Inspect unknown competition 556

Inspection now permits an unknown expected name as well as country/type. Run:

```powershell
python -B Backend/preview_api_football_competition.py --competition-id 556 --inspect
```

This attempts one `GET /leagues?id=556` request. It checks the returned numeric ID,
displays the provider-reported name/country/type and available seasons separately,
and reports `REVIEW REQUIRED` for each unspecified identity expectation. No name,
country or type is assumed for 556, and response values never become expectations
automatically. Missing results and API errors retain their existing handling.

Normal verification still requires a name and the other identity expectations.
The existing La Liga defaults and explicit Copa del Rey/Friendlies Clubs commands
remain supported. No internal competition ID, mapping, provider dataset or
database change is produced. Stop after preparing this inspection; review the
manual run's returned identity before any subsequent verification step.

## Step 28F.5.10.5 — Provider season identifiers and calendar dates

The previous preview compared `start.year` to provider `season.year`. That
incorrectly treated a season identifier as a mandatory calendar start year.
This comparison is removed: a season identified as 2024 can have both boundaries
in January 2025 without a warning solely for that reason. A league season can also
span two calendar years. No token, date or missing value is rewritten.

Date assessment now checks the following separately from competition identity:

- Valid YYYY-MM-DD boundaries and end date not preceding start date.
- Missing/null boundaries or absent season metadata: preserve unknown values and
  report precisely what cannot be assessed.
- Duplicate/invalid provider season IDs and malformed current flags: retain
  their existing review behavior.
- A date range longer than 732 days: request competition-specific review. This
  conservative local heuristic is not a universal limit or an invalidity claim.
- Any supplied boundary after the current **UTC date**: report an **unconfirmed
  provider schedule**, not independently verified events. For example, February
  2027 boundaries remain future schedule metadata when assessed in November 2026.

Dates after a provider season identifier's year are not automatically unusual or
invalid. Date checks do not independently establish event occurrence, even for
historical dates, and do not infer winners, coverage or competition-specific rules.
Identity can remain `VERIFIED` while individual season rows require review; the
overall command then exits 1 to retain that unresolved metadata warning.

The internal competition schema's `startYear` and `endYear` are actual calendar
boundary years, not provider season tokens. Their agreement with internal dates
remains correct and unchanged. Provider-to-internal season mapping is still future
work; no mapping is created by this correction.

Offline tests use fictional seasons, explicit as-of dates and a fixed UTC clock
for existing HTTP-mocked fixtures. They cover historical following-year editions,
future February schedules, missing data, date validity/order and all four identity
checks. No provider response is retrieved or persisted. Run the full suite:

```powershell
python -B -m unittest discover -s Backend -p "test_*.py" -q
```

Stop after Step 28F.5.10.5. This correction changes only local season assessment,
its tests and this documentation; API request limits and verification modes remain
unchanged. Competition identity and data reuse permissions remain separate checks.
