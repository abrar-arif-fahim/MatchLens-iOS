# MatchLens code audit — 17 November 2026

Reviewed the project context in `Markdown.md`, the backend Python modules and
tests, all local JSON input/output files, the schema/conversion/API documentation,
the SwiftUI screens and app entry point, and repository configuration. No live API
or Firestore operations were used. Existing datasets, credentials and Git history
were left unchanged.

## Fixed issues

| Issue | Correction |
| --- | --- |
| Importing the original API connection and Wikidata test scripts immediately read credentials or made network requests. | Both now use guarded `main()` functions and existing validated helpers. The API status test no longer prints account information. |
| The API key placeholder from `.env.example` was accepted as a real key, and the player script exited successfully after errors. | Reject placeholder variants regardless of case and invalid header whitespace; return a nonzero exit code on failures. |
| Older credential-bearing requests could follow redirects with the secret header. | Reuse a shared `NoRedirects` handler. Wikidata requests can still follow their ordinary redirects. No fallback requests were added. |
| A player search selected the first matching name even when multiple profiles matched. Incomplete pagination could also look like a complete search. | Require one unique matching profile and a complete, correctly typed response before proceeding. |
| The single-player pipeline accepted uncertain Wikidata birth dates as exact dates. | Reuse the batch preparer's strict calendar, precision, uncertainty and date checks. HTTP disconnects now produce a safe failure message. |
| Several input loaders silently accepted repeated JSON object keys; the batch player loader also allowed `Q0` and padded IDs. | Reuse the existing duplicate-field rejection helper throughout the older loaders, and require positive Q-numbers without leading zeros. |
| The single-player uploader could overwrite a document changed while the confirmation prompt was open. | Recheck document existence and version inside a single-attempt Firestore transaction, merge only the six managed fields, and cancel conflicts. Dry run, exact `YES` confirmation and read-back verification are retained. |
| Every match-library replay displayed City Blues' score and sample events, regardless of the selected card. | Pass the selected title to the replay and show City Blues' sample moments only for that match. Hide events outside the replay duration and label demonstration data clearly. |
| Extreme or nonfinite replay times could trap during integer/CMTime conversion. | Use the small `ReplayTimeline` helper to validate durations, clamp positions and format labels safely. |
| Favorites claimed cloud synchronization despite being stored only in view state. | Correct the text to say items are held in memory for the demo. |

The existing team-mapping preview re-exports the shared redirect handler, so its
other callers keep the same interface. Existing match/competition conversion and
schema behavior is preserved.

## Changed files

Backend: `api_football_players.py`, `api_football_test.py`, `wikidata_test.py`,
`prepare_player_data.py`, `prepare_multiple_players.py`, `prepare_team_data.py`,
`prepare_multiple_teams.py`, `discover_team_ids.py`, `import_players.py`,
`import_multiple_players.py`, `import_team.py`, `preview_multiple_teams.py`, and
`preview_api_football_team_ids.py`.

Frontend: `MatchLibraryView.swift`, `MatchReplayView.swift`, and
`FavoritesView.swift`. Added `MatchLensApp/Views/Replay/ReplayTimeline.swift`.

Added regression tests in `Backend/test_audit_regressions.py` and
`Tests/ReplayTimelineTests.swift`, plus this report.

## Verification

From the repository root in PowerShell:

```powershell
python -B -m unittest discover -s Backend -p "test_*.py" -q
```

Baseline: **109 tests passed**. After these fixes: **128 tests passed**. Regression
tests block real network/Firebase access and mock the transaction boundaries.
They cover import side effects, bad credentials, ambiguous/incomplete responses,
uncertain dates, duplicate keys, malformed IDs, cancellation, stale previews,
transaction conflicts, merge field restrictions and skipping unchanged records.

The Swift arithmetic checks can run separately with `swiftc` available on PATH:

```powershell
$replayTests = Join-Path $env:TEMP "MatchLens-ReplayTimelineTests.exe"
swiftc -parse-as-library MatchLensApp/Views/Replay/ReplayTimeline.swift Tests/ReplayTimelineTests.swift -o $replayTests
if ($LASTEXITCODE -ne 0) { throw "Swift compilation failed" }
& $replayTests
```

Actually executed using the installed Windows Swift compiler: **23 assertions
passed**. All **10 Swift app files passed syntax parsing**. All **29 Python files
passed compilation**, all **11 JSON files parsed without duplicate keys**, and
existing local match/competition validators and player/team loaders accepted the
repository data. No provider requests, credential reads or database operations
were needed for those checks.

## Remaining limitations

- The repository contains no `.xcodeproj` or `.xcworkspace`, and this Windows
  environment has no iOS SDK or Simulator. Swift syntax checks and arithmetic
  tests do not establish a successful SwiftUI type-check, iOS build or UI run.
  In the existing Mac Xcode project, include `ReplayTimeline.swift` in the same
  iOS app target as `MatchReplayView.swift`. Keep `Tests/ReplayTimelineTests.swift`
  outside that target because it has its own command-line test entry point.
- Login/registration remain local demos. Home/Profile/Favorites include explicit
  placeholder destinations; no highlight video is bundled, and saved items do
  not persist. These are unfinished integration work, not completed app features.
- The installed Google libraries warn that Python **3.10.11** is unsupported.
  An interpreter upgrade and a fresh dependency check remain environment work.
- Live API permissions, quotas, provider licensing and real Firestore transaction
  behavior were not exercised. Offline mocks cannot prove production connectivity.
- `Markdown.md` describes earlier roadmap work; the current backend also includes
  the later match/competition pipeline. This audit adds no development step or
  new external integration.

No commits, pushes, merges, Firebase changes or credential/configuration changes
were performed as part of this audit.
