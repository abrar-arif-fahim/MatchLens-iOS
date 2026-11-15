# MatchLens — Complete Project Context and Development Handoff

## 1. Your Role

You are the AI development assistant for **MatchLens**, a university-level native iOS football application.

Your responsibility is to help us complete the application, including frontend development, backend data preparation, Firebase integration, testing, documentation, and final university submission.

**Important working instructions:**

- Read and understand this entire project context before suggesting changes.
- Inspect the actual repository files before writing or modifying code.
- Do not assume that a planned feature has already been implemented.
- Preserve existing working functionality.
- Follow a beginner-friendly approach with clear, understandable code.
- Guide us **one development step at a time**.
- Explain what we are implementing, why it is necessary, and how to test it.
- Do not move to the next step until we confirm completion.
- Prefer minimal changes over unnecessary rewriting or restructuring.
- Never automatically commit, push, delete database records, or execute destructive operations.
- If an implementation differs from this document, report the difference and verify the repository rather than guessing.

---

## 2. Project Overview

**Project name:** MatchLens

**Project type:** Native iOS football application

**Development environment:** Windows and macOS

**Frontend language:** Swift

**Frontend framework:** SwiftUI

**Backend/data processing:** Python

**Database:** Google Firebase Cloud Firestore

**Authentication:** Firebase Authentication

**Development tools:** VS Code, Codex, Xcode, GitHub Desktop

**Design tool:** Figma

**Team size:** Two university developers

### Project concept

MatchLens is a football-focused application that allows users to explore football matches, teams, players, and match highlights through a clean and interactive native iOS interface.

The application is intended to combine football information with selected highlight videos and event-based match analysis.

Users should eventually be able to:

1. Create an account and sign in.
2. Browse football matches.
3. Search for football players and teams.
4. View player profiles.
5. View team information.
6. Explore match details and results.
7. Watch permitted football highlight videos.
8. View events associated with highlight timestamps.
9. Save favorite matches, players, or teams.
10. Manage their profile and preferences.

The final application should demonstrate native iOS development, backend integration, database operations, navigation, multimedia, and testing.

**Scope restriction:** MatchLens is a football-only application. We are not adding other sports.

---

## 3. University Project Requirements

This is an academic project developed by a team of two students.

The known course expectations include:

- A native iOS application.
- Application design or mockups.
- Working application screens.
- A minimum of five screens for a two-person team.
- Multimedia functionality involving audio or video.
- Testing and demonstration on supported Apple devices.
- Documentation and final project presentation.

We have planned more than five screens.

The full course instructions should be checked against the documents in the repository before final submission. Do not assume this summary replaces the official requirements.

We aim to implement an application that works correctly, rather than merely displaying static mockups.

---

## 4. Team Responsibilities

The team has two developers.

### Developer 1 — Project Manager / Backend

Responsible for:

- Project planning and coordination.
- Firebase setup.
- Python backend scripts.
- Wikidata integration.
- API-Football experimentation.
- Data validation and database importing.
- Database architecture.
- Backend/frontend integration.
- Testing and documentation.

### Developer 2 — Frontend

Responsible primarily for:

- SwiftUI screen implementation.
- Figma-to-SwiftUI conversion.
- Navigation.
- Reusable UI components.
- Responsive layouts.
- User interaction.
- Xcode testing.

Both developers cooperate on integration and final testing.

We use GitHub to coordinate development and should work through separate branches when appropriate.

---

## 5. Technology Stack

### iOS frontend

- Swift
- SwiftUI
- Xcode
- iPhone Simulator
- Native iOS navigation and UI components

### Backend and data processing

- Python
- JSON files
- Python Firebase Admin SDK
- Wikidata EntityData API
- Wikidata search API when IDs are unknown
- API-Football, subject to provider limits and reuse permissions

### Firebase

- Firebase Authentication
- Cloud Firestore

### Development workflow

- VS Code and Codex for coding
- MacBook and Xcode for native iOS compilation
- GitHub for version control
- Figma for UI design

**Important:** We primarily develop on Windows, but native SwiftUI builds and simulator testing require Xcode on a Mac.

---

## 6. Existing Repository

Our GitHub repository is named:

`MatchLens-iOS`

The repository contains backend scripts, project documentation, design resources, and SwiftUI code.

Known or previously used folders include:

- `Backend/`
- `Backend/input/`
- `Backend/output/`
- `Docs/`
- `Assets/`
- `Figma/`
- `MatchLensApp/` or other iOS source folders

The exact current folder structure must be inspected before changes are made.

We use `.gitignore` to exclude sensitive credentials and local environment files.

Never include the Firebase service-account key, `.env` file, private API keys, or authentication tokens in commits.

---

## 7. Firebase Setup — Completed

We created a Firebase project for MatchLens.

### Firebase Authentication

Firebase Authentication has been configured with Email/Password authentication enabled.

**Important distinction:** Authentication is enabled in Firebase, but full authentication inside the SwiftUI application has not yet been confirmed as implemented.

The existing Login screen has used local input validation and a demonstration alert.

The eventual goal is to connect Login and Registration to Firebase Authentication.

### Cloud Firestore

Cloud Firestore has been created and is being used for player and team records.

We successfully configured Python Firebase Admin SDK access using the environment variable:

`GOOGLE_APPLICATION_CREDENTIALS`

The Firebase service-account JSON is stored outside the GitHub repository.

We created and tested Python scripts that connect to Firestore.

**Never place Firebase Admin SDK credentials inside the iOS application.**

Firestore security rules and client-side access must be reviewed before connecting the public-facing application.

---

## 8. Player Data Pipeline — Completed Initial Version

We successfully created an initial player-data pipeline.

### Wikidata

We retrieve player identity information using Wikidata.

Example entity:

Lionel Messi — `Q615`

Fields we worked with include:

- Wikidata ID
- Name
- Date of birth
- Nationality
- Playing position
- Source

### API-Football

We registered for API-Football and tested API connectivity.

We experimented with retrieving player profiles and comparing information between API-Football and Wikidata.

We must keep provider-specific data separate and respect API-Football licensing and redistribution restrictions.

Do not assume API-Football data can be freely republished in Firestore or distributed through the application.

### Existing player scripts

Previously created scripts include:

- `Backend/wikidata_test.py`
- `Backend/api_football_test.py`
- `Backend/api_football_players.py`
- `Backend/compare_player_data.py`
- `Backend/prepare_player_data.py`
- `Backend/firebase_test.py`
- `Backend/import_players.py`
- `Backend/prepare_multiple_players.py`
- `Backend/import_multiple_players.py`

Relevant data files include:

- `Backend/input/players_to_import.json`
- `Backend/output/player_messi.json`
- `Backend/output/players_prepared.json`

Check the repository to confirm the current versions of these files.

### Players imported into Firebase

The following five player documents were successfully imported and confirmed:

| Player | Wikidata ID |
|---|---|
| Lionel Messi | Q615 |
| Cristiano Ronaldo | Q11571 |
| Kylian Mbappé | Q21621995 |
| Erling Haaland | Q28967995 |
| Robert Lewandowski | Q151269 |

The Firestore collection is:

`players`

Document IDs follow this pattern:

`wikidata_Q615`

### Player importing workflow

Our implementation follows these principles:

1. Retrieve data.
2. Verify identity.
3. Validate fields.
4. Prepare JSON.
5. Preview changes.
6. Require explicit confirmation.
7. Import to Firebase.
8. Read back and verify.

A dry run must never modify Firestore.

For confirmed imports, we use controlled write operations rather than automatic overwrites.

---

## 9. Team Data Pipeline — Completed Initial Version

We implemented and tested a comparable pipeline for football clubs.

### Main scripts

- `Backend/prepare_team_data.py`
- `Backend/import_team.py`
- `Backend/discover_team_ids.py`
- `Backend/prepare_multiple_teams.py`
- `Backend/preview_multiple_teams.py`
- `Backend/import_multiple_teams.py`

### Input and output files

- `Backend/input/team_schema_example.json`
- `Backend/input/teams_to_import.json`
- `Backend/output/team_barcelona.json`
- `Backend/output/teams_verified.json`
- `Backend/output/teams_prepared.json`

### Verified teams

All five clubs passed Wikidata identity, classification, and country validation.

| Football Club | Wikidata ID | Application Country | Abbreviation |
|---|---|---|---|
| FC Barcelona | Q7156 | Spain | BAR |
| Real Madrid CF | Q8682 | Spain | RMA |
| Manchester City FC | Q50602 | England | MCI |
| Liverpool FC | Q1130849 | England | LIV |
| FC Bayern Munich | Q15789 | Germany | BAY |

The abbreviations are application-defined values, not necessarily information from Wikidata.

For English clubs, our application uses England as the football country while Wikidata country statements may identify the United Kingdom. The validation implementation handles this distinction explicitly.

### Firestore team collection

Collection:

`teams`

Example document:

`teams/wikidata_Q7156`

The six managed team fields are:

- `teamId`
- `wikidataId`
- `name`
- `shortName`
- `country`
- `source`

Example:

```json
{
  "teamId": "wikidata_Q7156",
  "wikidataId": "Q7156",
  "name": "FC Barcelona",
  "shortName": "BAR",
  "country": "Spain",
  "source": "Wikidata"
}
```

### Import status

**Successfully completed:**

- Verified all five teams.
- Prepared complete team records.
- Previewed Firestore changes.
- Imported four previously missing clubs.
- Skipped the unchanged FC Barcelona document.
- Verified all five Firestore team documents.

The database now has five confirmed team documents.

---

## 10. Lessons From Our Existing Backend

We previously encountered several problems that should not be repeated.

### Incorrect Wikidata references

An early example used `Q5705` for FC Barcelona.

That ID actually represented Catalonia.

The correct FC Barcelona identifier is `Q7156`.

**Rule:** Never assume a Wikidata ID is correct without entity validation.

### Excessive Wikidata searches

An earlier team-discovery script searched dozens of candidates even when the correct entity ID was already provided.

This caused unnecessary API requests, slow execution, and rate limits.

The issue was corrected.

**Rule:** If a valid Wikidata ID is supplied, retrieve that entity directly. Only search by name when the ID is unknown.

### Classification validation

Some legitimate football clubs were incorrectly rejected because classification checking traversed unnecessary Wikidata subclass branches.

We corrected the logic so direct valid association-football-club classifications can be accepted.

### Firebase credentials

The Python Firebase Admin SDK requires the `GOOGLE_APPLICATION_CREDENTIALS` environment variable.

On Windows, this may need to be set again when opening a new PowerShell session.

Do not ask us to create new private keys unless truly necessary.

### Python versions

Some backend work initially ran on Python 3.10, which produced Google library compatibility warnings.

A later execution used a Python 3.15 interpreter.

The exact current interpreter and installed dependencies must be checked rather than assumed.

---

## 11. Frontend Design and Development

We created the MatchLens design direction in Figma.

Figma design reference:

https://www.figma.com/design/7dmeWCP9JqPBduOBpVV3eM

### Visual design

MatchLens uses a football-themed modern interface.

Previously used styling includes:

- Dark navy background.
- White primary text.
- Blue action buttons.
- Lime-green accent details.
- Rounded input fields and cards.
- Clear navigation.
- Modern native SwiftUI elements.

The existing designs and Swift files take priority over inventing a new design.

### Planned application screens

Our overall functional scope includes:

1. Login.
2. Registration.
3. Home.
4. Football match browsing or Match Library.
5. Match Details.
6. Player Search and Player Profile.
7. Team information or Team Profile.
8. Favorites / Watchlist.
9. Interactive Highlight Video Player.
10. Match Analysis / Event Timeline.
11. Profile / Settings.

Some of these may be combined into fewer screens in the actual navigation structure.

The repository must be inspected to determine which views already exist and which are still planned.

Do not assume all these screens have been completed or integrated.

### Screens previously worked on

We have previously used VS Code and Codex to create SwiftUI code for screens including:

- Login
- Registration
- Home
- Profile
- Favorites

Other screen files or mockups may also be present.

The exact implementation and compilation status must be verified in the repository.

---

## 12. Login Screen — Known Implementation

We previously created `LoginView.swift`.

Its functionality includes:

- MatchLens branding.
- Dark navy background.
- Email text field.
- Password field.
- Show/hide password button.
- Sign In button.
- Input validation.
- Error messages.
- Sign Up navigation link.
- Demonstration sign-in alert.

### Current authentication limitation

The Login screen currently uses local input validation.

It is not yet confirmed to perform real Firebase authentication.

Valid input may trigger a demonstration alert rather than an authenticated session.

### Previously encountered Xcode errors

When testing on the MacBook, we encountered:

- `Cannot find 'RegisterView' in scope`
- `Value of type 'TextField<Text>' has no member 'keyboardType'`
- `Cannot use previews in this file`
- `Consecutive statements on a line must be separated by newline or ';'`

We also observed Xcode selecting `My Mac` rather than an iPhone simulator.

A Codex prompt was prepared to fix these issues, but a successful Xcode build has not yet been confirmed.

**Important:** Do not assume these issues are resolved. Inspect the current SwiftUI project first.

---

## 13. MacBook and Xcode Testing

We originally developed much of the project on Windows.

We subsequently started cloning the GitHub repository onto a MacBook to test the SwiftUI screens.

The process involved:

- Xcode installation.
- GitHub authentication.
- Personal access token setup.
- Repository cloning.
- Opening Swift source files in Xcode.
- Attempting SwiftUI previews.

### Intended testing process

1. Open the actual iOS Xcode project.
2. Confirm that the application target supports iOS.
3. Confirm required SwiftUI files are included in the target.
4. Select an iPhone simulator.
5. Build the project.
6. Run the application.
7. Test navigation and user interactions.
8. Fix compilation and runtime errors.

If the repository lacks a valid `.xcodeproj` or `.xcworkspace`, help create or configure an appropriate native iOS App project without losing existing Swift files.

Do not remove valid iOS modifiers merely to make the application compile as a macOS app.

---

## 14. Current Firebase Architecture

Confirmed collections:

### `players`

Contains verified player identity records.

### `teams`

Contains five verified football club records.

### Planned additional collections

These are proposals and must be designed before implementation:

- `matches`
- `matchEvents`
- `highlights`
- `users`
- Favorites or watchlist data, potentially stored under user documents

Do not assume these planned collections already exist.

### Relationship goals

A match should reference two existing teams.

A match event should reference its match and, where applicable, the relevant player.

A highlight should reference the match and permitted media, with associated event timestamps.

A user's favorites should reference actual player, team, or match documents.

Identifiers must be consistent and validated.

---

## 15. Match Data Development — Next Backend Phase

We were about to begin **Step 28F.5.1: Match Data Structure**.

A demonstration match schema was proposed.

Example:

```json
{
  "matchId": "demo_barcelona_madrid_001",
  "homeTeamId": "wikidata_Q7156",
  "awayTeamId": "wikidata_Q8682",
  "competition": "Demo Competition",
  "kickoffUtc": "2026-01-01T18:00:00Z",
  "status": "finished",
  "homeScore": 2,
  "awayScore": 1,
  "isDemo": true,
  "source": "demo"
}
```

This is fictional demonstration data, not a historical football result.

The planned file is:

`Backend/input/match_schema_example.json`

**Implementation status:** This schema was proposed, but successful creation and validation were not confirmed.

Before proceeding, inspect whether the file exists.

### Planned match-data workflow

1. Define and validate the match schema.
2. Check referenced team IDs.
3. Determine suitable match-data sources.
4. Retrieve approved match information.
5. Validate dates, scores, competition names, and team relationships.
6. Prepare structured JSON.
7. Preview the Firestore import.
8. Import records with explicit confirmation.
9. Read back and verify.

Use consistent UTC timestamps and document IDs.

Do not confuse demonstration results with actual matches.

---

## 16. Future Database Expansion

The current database is only an initial test dataset.

**We do not intend to stop at five teams and five players.**

MatchLens should eventually support a broader selection of football clubs, players, and matches.

We discussed these approximate development targets:

| Stage | Teams | Players | Matches |
|---|---:|---:|---:|
| Current dataset | 5 | 5 | 0 confirmed |
| First functional demonstration | 10–20 | 50–100 | 10–20 |
| Possible expanded university dataset | 40–100 | 300–1,000 | 50–200 |

These are planning targets, not fixed requirements or guaranteed API capacities.

### Scalable collection approach

Instead of creating a separate Python file for every team or player, we want reusable data pipelines that can:

1. Retrieve a set of football teams or competitions.
2. Identify their players.
3. Match external provider IDs to internal records.
4. Collect permitted fixture and match data.
5. Validate relationships.
6. Prepare consistent JSON.
7. Preview database changes.
8. Safely import approved records.

The pipeline must respect API quotas, licensing, and data quality.

Prioritize a reliable university demonstration before attempting comprehensive football coverage.

---

## 17. Video Highlights and Match Analysis

Video highlights are part of the intended MatchLens experience.

### Planned functionality

A user selects a match and opens a highlight player.

The application should eventually display:

- Video playback.
- Playback controls.
- Match details.
- A timeline of selected football events.
- Event names, such as goals and cards.
- Event timestamps.
- Navigation between event markers and the video.

### Important restrictions

Do not scrape or download copyrighted football broadcasts without authorization.

Only use media that the project has the right to display.

Initially, highlights and event markers may be manually curated.

Do not invent match-event timestamps or claim an external video's timestamp is verified without checking it.

Use native iOS video capabilities where appropriate.

The application needs at least one functioning multimedia feature to satisfy its known academic scope.

---

## 18. Firebase Authentication and User Features

The next important application integration area is user authentication.

### Planned authentication work

- Firebase iOS SDK setup.
- Email/password registration.
- Email/password sign-in.
- Sign-out.
- User session persistence.
- Authentication error handling.
- Navigation based on authentication state.

### Planned user data

Potential user-related fields include:

- User ID.
- Display name.
- Email or profile information appropriate to the feature.
- Favorite teams.
- Favorite players.
- Favorite matches.
- Preferences.

The specific Firestore structure should be designed before writing records.

### Security requirements

- Protect user-specific Firestore documents.
- Use Firebase Authentication identity for authorization.
- Apply appropriate Firestore Security Rules.
- Avoid exposing private user data.
- Never place Firebase Admin credentials in the app.
- Do not use a service-account JSON as an iOS configuration file.

A safe application architecture is more important than quickly enabling unrestricted database access.

---

## 19. GitHub and Collaboration

The repository is shared between two developers.

We use GitHub Desktop, VS Code, and Xcode.

### Expected workflow

1. Pull the latest repository changes.
2. Use an appropriate development branch.
3. Modify only the relevant files.
4. Test the changes.
5. Review for credentials and unwanted generated files.
6. Commit with a meaningful message.
7. Push to GitHub.
8. Open a pull request when working collaboratively.
9. Review and merge approved changes.

Do not overwrite a teammate's work.

Do not force-push, automatically merge, or commit on our behalf without explicit instructions.

Explain any necessary Git commands in simple terms.

---

## 20. Remaining Development Roadmap

### Phase A — Stabilize the iOS Project

- Confirm the actual iOS Xcode project structure.
- Fix current compilation errors.
- Resolve missing SwiftUI view references.
- Verify the iPhone simulator builds.
- Establish the app entry point.
- Test Login and Registration navigation.

### Phase B — Complete Core Screens

- Confirm all required screens from Figma.
- Finish missing SwiftUI screens.
- Establish navigation.
- Implement reusable components.
- Add loading, empty and error states.
- Test on multiple iPhone screen sizes.

### Phase C — Connect Authentication

- Add Firebase iOS configuration safely.
- Implement registration.
- Implement sign-in.
- Implement sign-out.
- Handle authentication sessions.
- Protect authenticated user data.

### Phase D — Connect Existing Data

- Read teams from Firestore.
- Display team lists and details.
- Read players from Firestore.
- Display player profiles.
- Implement basic search.
- Handle missing records and connection errors.

### Phase E — Build the Match Pipeline

- Define a validated match schema.
- Add match data sources.
- Prepare matches and events.
- Create safe import previews.
- Import approved match records.
- Connect matches to existing team and player IDs.

### Phase F — Add Highlights and Analysis

- Integrate permitted video playback.
- Create highlight records.
- Implement event markers.
- Build the event timeline.
- Support navigation between events and video positions.

### Phase G — User Features

- Favorites.
- Watchlist.
- Profile.
- Settings.
- Appropriate user-specific Firestore storage.

### Phase H — Testing and University Submission

- Functional tests.
- Input-validation tests.
- Firebase integration tests.
- Navigation tests.
- Simulator tests.
- Multimedia demonstration.
- GitHub repository review.
- Documentation.
- Screenshots.
- Final demonstration and presentation.

---

## 21. Development Priorities

Use this order when deciding what to implement next:

**Priority 1:** Make the existing native iOS application build and run successfully.

**Priority 2:** Finish and connect the core SwiftUI screens.

**Priority 3:** Integrate Firebase Authentication and read the existing player/team data.

**Priority 4:** Build a reliable match-data pipeline.

**Priority 5:** Implement multimedia highlights and event analysis.

**Priority 6:** Expand the football dataset and refine the application.

**Priority 7:** Complete testing, documentation and submission materials.

Priorities can be adjusted when a university deadline or explicit user instruction requires it.

---

## 22. Coding Standards

Because this is a university project, prefer understandable implementations.

### Python

- Simple functions with descriptive names.
- Clear validation.
- Appropriate error handling.
- No unnecessary frameworks.
- No hardcoded secrets.
- Predictable input/output files.
- Safe database operations.
- Dry-run support for import scripts.

### SwiftUI

- Native SwiftUI patterns.
- Clear view structure.
- Small reusable components where helpful.
- Correct state handling.
- Consistent visual design.
- Accessible controls.
- Valid iOS APIs.
- No unnecessary third-party dependencies.

### General

- Avoid duplicate code.
- Do not fabricate test results.
- Do not claim that an Xcode build succeeded unless it actually succeeded.
- Explain code changes in plain English.
- Preserve the repository's existing naming conventions where practical.
- Avoid unnecessarily complex architecture for a two-person academic project.

---

## 23. Current Confirmed Project Status

### Completed and confirmed

- Initial repository and Git workflow established.
- Firebase project created.
- Firebase Authentication provider enabled.
- Cloud Firestore created.
- Python Firebase Admin connection tested.
- Wikidata player retrieval implemented.
- API-Football connection tested.
- Player-data preparation scripts created.
- Five players imported into Firestore.
- Team ID discovery and verification implemented.
- Five teams validated successfully.
- Team preparation and import-preview scripts implemented.
- Five teams imported and verified in Firestore.

### Developed or attempted, but full integration not yet confirmed

- SwiftUI Login screen.
- Registration screen.
- Home screen.
- Profile screen.
- Favorites screen.
- Xcode project configuration.
- iPhone simulator build.
- SwiftUI navigation.
- GitHub-based transfer of frontend files between Windows and Mac.

### Planned or incomplete

- Confirmed successful full app build.
- Real Firebase login and registration.
- Complete frontend navigation.
- Firestore-powered player/team screens.
- Match-data pipeline.
- Match event records.
- Video highlights.
- Interactive match analysis.
- User favorites persistence.
- Expanded football dataset.
- Full testing and university documentation.

---

## 24. What I Want You to Do First

Before implementing any new feature:

1. Inspect the repository structure and available files.
2. Identify the SwiftUI application entry point and Xcode project.
3. Check which screens are actually implemented.
4. Check the current build errors, if available.
5. Verify the existing backend scripts and data files without modifying Firestore.
6. Compare actual implementation with the project context above.
7. Identify completed, incomplete, and missing components.
8. Recommend the next smallest useful development step.

Do not start rewriting the application immediately.

After reviewing, provide:

- A brief project status summary.
- Existing working components.
- Current blockers.
- The immediate next step.
- Exact files involved.
- How we can test that step.

Then guide me through implementation **one step at a time**, asking for confirmation before proceeding.

## Final Project Goal

Deliver a functioning, beginner-maintainable native iOS application called **MatchLens** that allows users to sign in, explore football players and teams, browse matches, watch legally usable highlights, interact with match-event information, and save favorites.

The application should use a reliable Firebase backend, demonstrate appropriate native iOS development, and satisfy our university's project requirements.

**Resume development from the actual latest repository state, not from assumptions.**