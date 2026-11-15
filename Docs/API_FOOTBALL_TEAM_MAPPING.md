# API-Football team ID mapping preview — Step 28F.5.4

Run manually from the repository root:

```powershell
python Backend/preview_api_football_team_ids.py
```

The preview reads the five references from `Backend/output/teams_verified.json`
using the existing verified-team loader. It reuses `read_api_key()` from
`api_football_players.py`, which reads `API_FOOTBALL_KEY` from the root `.env`.
The key goes only in the `x-apisports-key` request header and is never displayed.
No packages, new credentials or Firebase connection are needed.

## Requests and identity checks

### Optional targeted Bayern Munich check

If the normal English-name search does not return Bayern, run:

```powershell
python Backend/preview_api_football_team_ids.py --verify-bayern
```

This separate mode makes at most one request: `GET /teams?id=157`. The lookup ID
is the documentation-provided candidate; it is not automatically treated as a
verified mapping. The local Wikidata reference remains `Q15789`.

The provider must return exactly one complete record with numeric ID 157,
Germany, a Bayern Munich name and `national: false`. Existing normalization
accepts Bayern Munchen/München, Bayern Munich and FC Bayern München. Women's,
youth, reserve, national or unrelated teams cannot pass. Optional provider code,
founding year and venue city are displayed as hints, not independently verified
facts. Missing, contradictory, duplicate or incomplete evidence gives REVIEW
REQUIRED; API/configuration failures give ERROR. Only a confirmed response gives
VERIFIED. Nothing is saved.
Exit code 0 in this mode means Bayern alone passed; 1 means review or error.

There are no name searches, retries, redirects or additional pages in this mode.
It does not call the other four mappings. The command without flags keeps the
existing five-team search behavior and five-request limit unchanged.

### Normal five-team search

The provider documents team-name search using `GET /teams?search=...` with at
least three characters. Parameters are URL-encoded. See the
[API-Football documentation](https://www.api-football.com/documentation-v3#tag/Teams)
and its [official endpoint guide](https://www.api-football.com/news/post/how-to-get-started-with-api-football-the-complete-beginners-guide).

- At most five requests: one normalized name search per club, with a 20-second
  timeout and a two-second pause between requests. Results are cached only in
  memory for the current run. No status/preflight requests are made.
- No retries, fallback searches, candidate lookups or additional pages are
  requested. Incomplete pages and malformed/duplicate candidate IDs prevent a
  VERIFIED result, even when the first candidate looks correct.
- All returned candidates are considered. Existing accent/punctuation and club
  designator normalization supports FC/CF/F.C., Club de Futbol, and
  Munchen/Munich spellings. Distinctive words must still match exactly. There is
  no fuzzy, substring, abbreviation-only or first-result identity selection.
- National teams and names identifying women's, reserve, youth or other sports
  sections are rejected. A compatible club requires the provider's boolean
  `national` flag to be false. Missing identity evidence requires review.
- Country must match the existing validated application country. United Kingdom
  or Great Britain alone is insufficient to establish England; this is reported
  for review rather than silently changing either country's value.
- Provider team code, founding year and venue city are displayed as optional
  provider hints. They are not independently verified facts. In particular, the
  application's shortName is not required to equal the provider's team code.
- Multiple plausible candidates, incomplete evidence, or one provider ID
  apparently mapping to different Wikidata clubs require manual review.

## Interpreting the terminal output

The table shows the expected club, Wikidata ID, candidate API-Football ID, provider
name/country and status. Multiple rows can belong to the same expected club.
Rejected candidates use NOT FOUND to indicate that candidate did not match;
per-club reasons and the final club summary describe the overall outcome.

| Status | Meaning |
| --- | --- |
| VERIFIED | Exactly one compatible candidate in a complete returned search, with no unresolved plausible alternatives. Identity check only; not permission to publish. |
| REVIEW REQUIRED | Ambiguous/incomplete results or missing identity evidence. No mapping is accepted. |
| NOT FOUND | No compatible candidate in the complete returned search. Does not prove the club is absent from the entire provider database. |
| ERROR | API/access/network/configuration error, or the club was not searched after earlier API errors or quota exhaustion. |

The normal preview's final summary counts clubs, not candidate rows. Exit code 0 means all five
clubs passed; 1 means at least one requires attention or the preview failed.
Actual provider IDs come only from the responses. No example IDs are guessed.

HTTP authentication/access errors, unavailable endpoints, HTTP 429, exhausted
quota headers and provider errors returned with HTTP 200 are handled safely.
An error stops remaining requests to conserve quota. A valid response that uses
the last allowed request can still be assessed, but remaining clubs are not
searched. Check the existing dashboard/plan and retry manually later; repeated
manual runs also consume quota. Raw errors/responses and request headers are
never printed.

## Storage and permissions

This script prints a preview only. It does not write JSON output or cache files,
save provider mappings/responses, connect to Firebase/Wikidata, change existing
team/player records, retrieve fixtures, or collect logos/images. Any image URLs
present in an API response are ignored. The Wikidata ID and API-Football ID remain
separate identifiers from separate sources.

Before persisting mappings or provider data in Firestore, exporting them to a
dataset, or shipping them in the iOS application, review the applicable plan and
[API-Football terms](https://www.api-football.com/terms), and ask the provider when
the intended storage/redistribution use is unclear. The terms prohibit resale
without permission and note possible third-party rights in data and branded
content. API access or a successful identity check is not licensing clearance.

Stop after Step 28F.5.4. This preview does not start match collection/importing.
