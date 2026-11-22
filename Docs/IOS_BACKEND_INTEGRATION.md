# MatchLens core backend and iOS integration

## Verified status

Reviewed Markdown.md completely, relevant preparation/import/preview modules,
match/event/highlight services and tests, the eight existing SwiftUI screen
implementations, and the Xcode target. The branch started clean on main at
8d8d96e. The baseline actually passed **223 tests, OK**.

The full suite now passes **298 tests, OK**, including 75 new offline tests.
The fictional app workflow ran successfully. Node syntax checking passed for the
optional emulator test file. **Rule compilation and emulator assertions have NOT
run:** Firebase CLI, its test packages and a cached emulator are absent. No tools
were downloaded.

| Component | Implemented offline | Still missing / unverified |
| --- | --- | --- |
| Login / registration | Session handoff, safe errors, owner-scoped idempotent profile provisioning/recovery | Swift SDK setup and actual account creation/sign-in/sign-out |
| Home / library | Bounded feed, pagination, team/competition joins, empty/error states, demo separation | Approved match documents and client wiring |
| Player search / profiles | Accent-insensitive bounded-page search, identity details, managed-field allowlist | Expanded catalog and verified roster/statistics data |
| Team information | Identity/abbreviation search, separate home/away match pages | Verified roster data and client UI |
| Match details | UTC/null/period-score handling, competition/team/player links, events and highlight timelines | Approved real events, lineups and statistics |
| Highlights | Metadata/marker validation; no media reference in app DTOs | Rights, actual assets and playback testing |
| Favorites / watchlist | Deterministic references, desired saved state, stale-target handling, conflicts | Swift transaction executor and deployed rules |
| Profile / settings | Display name, favorite team, appearance and notification preferences | Client persistence and any actual notification delivery |
| Access control | Draft rules/indexes and 11 optional emulator security tests | Emulator verification, deployment and client authorization testing |

Numbered Phase 29 remains undocumented. Roadmap Phases C–G have offline backend
contracts, not demonstrated full application completion. Phase H still needs
Firebase, device, navigation and multimedia testing.

## Architecture

Use **Firebase Authentication and Cloud Firestore through the Firebase Swift
SDK** in iOS. There is no hosted HTTP backend in this repository and no need for
a new REST API.

Python remains the preparation/validation toolchain and executable reference
implementation of app data contracts. These functions are not remote endpoints
and do not run inside SwiftUI. Swift repository implementations should mirror
their operations against Firebase.

- Auth handles passwords, email identity and sessions. Passwords never go to
  Python or Firestore.
- Every private path derives from the current authenticated Firebase UID.
- Python actor_uid models an already authenticated caller for offline tests.
  It does not authenticate anyone or verify tokens. Do not expose a server
  accepting an arbitrary actor_uid from a request.
- Admin SDK clients bypass security rules. The new Admin adapter is public-read-only,
  rejects private collections and requires an explicitly supplied existing client.
- Actual client authorization requires deployed, emulator-tested rules using
  request.auth.uid. Never put Admin credentials or API-Football keys in iOS.

The current Xcode target uses **com.example.MatchLens** and has no Firebase package
references. Confirm the registered Firebase iOS app/bundle identifier before
configuration. Add the official FirebaseAuth and FirebaseFirestore products and
the correct iOS client configuration in a later integration batch, then initialize
Firebase once. No Xcode or Swift files were changed here.

## Read services

app_contracts.py shares IDs, managed projections, UTC handling and normalization,
reusing existing player/team/match validators. Existing schemas remain unchanged.

app_repository.py defines get/page, isolated MemoryRepository, and
FirestoreReadRepository. Queries fetch at most 51 documents (50 plus lookahead),
with timeout and no retry. Arbitrary collection paths/filters are rejected.

AppReadService takes a repository, the existing reviewed competition catalog,
actor_uid and an explicit demo_mode (default false). Results are copies.

| Interface | Result |
| --- | --- |
| get_player(playerId) | player, nullable team/statistics, rosterStatus=notCollected |
| get_team(teamId) | team, nullable players, rosterStatus=notCollected |
| search_players / search_teams | items, nextCursor, hasMore, searchScope, scanned, issues |
| list_matches | Paged match/homeTeam/awayTeam/competition/competitionSeasons bundles |
| home_feed | matches page, isDemo, dataLabel, empty featuredHighlights, mediaMessage |
| team_matches | Separate home/away pages with independent cursors |
| get_match_detail | Joined match, eventPlayers, paged events/highlights, timelines, nullable statistics/lineups, demo label |
| resolve_reference(kind, id) | Validated player/team/match or safe highlight summary |

### Fields and pagination

- Team/player IDs stay wikidata_Q...; the player DTO adds playerId from its document
  ID. Stored players retain their original six fields. Provider extras/photos are
  excluded from projected player/team DTOs.
- Matches retain the existing 21 fields. Internal matchId and external sourceMatchId/
  sourceCompetitionId stay separate. Scores remain nullable integers, with regular
  time, extra time and shootouts separate. Required nulls must not be omitted.
- SDK kickoff Timestamps become whole-second UTC strings in Python DTOs.
  Unknown postponed/cancelled kickoffs stay null. Naive timestamps or unsupported
  subsecond kickoff precision fail validation.
- User Timestamp DTOs use UTC ISO strings with nine fractional digits, preserving
  nanoseconds. Swift transaction comparisons should retain native SDK Timestamps
  rather than roundtripping expected values through Date/JSON.
- Seasons remain separate reviewed catalog records. Empty lists indicate missing
  mappings. Rosters/statistics/lineups are unavailable, never inferred.
- Search scans at most 50 source documents per call and normalizes accents/case/
  whitespace locally. searchScope is boundedCatalogPage. Empty items with hasMore
  true do not mean no global result exists. Continue paging; reset the cursor when
  the query changes. Firestore does not provide this substring search automatically.
- Search/private lists use document-ID order. Matches use kickoff descending then
  document ID descending. Missing or foreign-query cursors require refresh.
- The default match catalog uses isDemo=false. Explicit demo mode reads only demo
  data; detail lookups check this too. Display the provided fictional-data label.
- Feed validation issues are explicit. Connectivity failures stop the operation.

### Match details and media

Event/highlight pages have separate cursors. Marker events outside the visible
page are resolved once, including their player identities, within a 100-link
budget. Existing analysis validators check the complete relationships. Football
clocks and video seconds stay independent; partial events never recalculate scores.

The app contract supports **metadata-only highlights**. Queries require
rightsStatus=unconfirmed and mediaReference=null, plus matchId for details.
The draft rules require those media constraints. App DTOs exclude media references
and rights evidence and always return playbackAvailable=false. An authorized
metadata claim alone does not demonstrate actual permission or media availability.
No trending highlights or video positions are invented.

## Authentication and private storage

auth_contracts.session_view accepts exactly uid/email/emailVerified projected from
the **current Firebase Auth User**, never a form, cached UID or unverified token:

- No Auth user: signedOut; old private profile state is discarded.
- Auth user but missing profile: profileRequired; provisioning can be retried.
- Matching validated profile: ready.
- Profile from a different UID: access error.

Safe errors map Auth SDK case names. Wrong-password, user-not-found and
invalid-credential cases share a message. Raw SDK errors/tokens are not displayed.

Registration calls Firebase Auth first, then provisions the profile. If profile
writing fails, recover it using the current Auth user rather than repeatedly
creating accounts. Sign-in reads that owner's profile. Sign-out/account changes
must cancel old listeners, clear private UI state and reject delayed results
belonging to the old UID. Review disk-cache privacy before release.

UserDataService supplies reads and plans with ownership checked before private
reads. simulate_user_plan applies plans to a **copy of local dictionaries**,
rechecking expected state and references.

| Path | Exact stored fields |
| --- | --- |
| users/{uid} | uid, displayName, schemaVersion=1, createdAt, updatedAt |
| users/{uid}/settings/preferences | favoriteTeamId (nullable), scoreNotifications (bool), highlightNotifications (bool), appearance (system/dark/light), schemaVersion=1, updatedAt |
| users/{uid}/favorites/{targetType}_{targetId} | targetType (player/team/match/highlight), targetId, schemaVersion=1, createdAt |
| users/{uid}/watchlist/{matchId} | matchId, schemaVersion=1, createdAt |

Email remains authoritative in Auth. Passwords, roles, tokens, API keys and
arbitrary private fields are rejected. Missing settings have explicit non-persisted
defaults: notifications off, system appearance, no favorite team. Preferences do
not schedule notifications.

Methods: profile, settings, plan_profile, plan_settings, plan_favorite,
plan_watchlist and paginated saved_items. Favorites/watchlists use desired saved
state instead of toggles. Matching records produce NO CHANGE. Missing targets
cannot be newly saved; stale saved targets display unavailable and can be removed.

### Future Swift mutation executor

Plans contain path/operation/data/serverTimestampFields/expected. They are **not
uploads**; no Firebase writer is implemented in this batch.

1. Bind the operation to Firebase Auth's current UID.
2. In a client transaction, re-read the exact owned document and compare managed
   state with the expected snapshot. Refresh on conflict.
3. CREATE requires absence, UPDATE existence, NO CHANGE issues no write.
   Favorite/watchlist documents are immutable after creation; removal is DELETE.
4. Supply FieldValue.serverTimestamp() for listed timestamp fields. They are
   omitted from plan data; no placeholder timestamps are stored.
5. Profile/settings UPDATE data is a patch. Preserve createdAt and do not replace
   documents using serialized read DTOs.
6. Deployed rules recheck ownership, exact fields, types, server time and targets.

Actual Swift execution, retry behavior and live read-back still need testing.
Account deletion/cleanup is outside this contract; profile deletion is denied.

## Draft Firebase rules and tests

Firebase/firestore.rules denies unauthenticated access, public catalog writes,
other users' private data, profile listing, unknown private fields, arbitrary
descendants and unbounded lists. List limits cannot exceed 51. Actual media
references remain blocked.

**Rules cannot redact fields.** Signed-in catalog reads return entire documents;
Python projection is not a Firestore security filter. Audit existing public
documents for provider extras/private data before deployment or iOS connection.
Admin ingestion must publish only validated, approved public content. The live
database was not inspected in this batch.

The index file covers match feed/status/home/away ordering and metadata-only
highlight queries. No rules or indexes were deployed.

Optional tests only target a loopback emulator and project demo-matchlens. After
manually installing a supported JDK, set up/run from the repository root:

~~~powershell
Set-Location Firebase
npm install --no-save --package-lock=false firebase @firebase/rules-unit-testing firebase-tools
npx --no-install firebase emulators:exec --config firebase.emulator.json --only firestore --project demo-matchlens "node --test tests/firestore.rules.test.mjs"
Set-Location ..
~~~

This manual setup downloads developer tools/emulator artifacts and was **not
performed**. Tests reject non-loopback hosts and use fictional local documents.
They cover ownership, guests, protected fields/server time, favorites/watchlist,
bounded queries and media denial. They do not test real Auth or production data.
Resolve all emulator failures and review production rules before deployment.

## Commands actually executed

~~~powershell
python -B Backend/preview_app_workflow.py
python -B -m unittest discover -s Backend -p "test_*.py" -q
node --check Firebase/tests/firestore.rules.test.mjs
~~~

The fictional workflow succeeded, 298 Python tests passed with final result OK,
and JavaScript syntax checking succeeded. Emulator rule assertions did not run.
Existing Python 3.10.11 Google-library support warnings did not fail the tests.

## Next integration batch

Ready for **offline app workflow tests**, not live end-to-end testing.

1. Run emulator security tests and audit existing public documents.
2. Configure Firebase in iOS and implement Swift repositories, Auth/session
   lifecycle, owned transactions and listener cleanup using these contracts.
3. Manually deploy reviewed rules/indexes; demonstrate two-user access,
   registration/sign-in/sign-out and saved/settings persistence/read-back.
4. Confirm provider permissions and provision approved competition/match/event
   data in a separately authorized step.
5. Supply legally usable media and demonstrate iPhone playback separately.
6. Add verified rosters, lineups and statistics only from approved sources.

No Swift/Xcode settings, existing data, credentials or live Firebase settings were
changed. No external requests, provider-data persistence or real Firestore writes
occurred.
