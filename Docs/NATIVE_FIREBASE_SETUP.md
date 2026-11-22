# Native Firebase integration: source ready for Mac validation

The existing eight SwiftUI screens now use a shared AppStore and native Firebase
services. Login/Registration keep their existing forms and designs. Home, Library,
Saved and Profile share one tab bar rather than opening duplicate tab screens in
sheets. The new catalog, player/team profiles and match-detail route fill missing
destinations. Dark navy cards, blue buttons, lime accents and ML branding remain.
Appearance preferences now also support light/system colors.

**This is source integration, not a demonstrated working iOS build.** Xcode and
the iOS SDK are unavailable on this Windows machine. Swift syntax parsing and
Foundation-only tests passed; Firebase SDK type-checking, linking, simulator/device
behavior and all live Firebase operations remain pending. No app was launched,
Auth account created, database written or rules/indexes deployed by this batch.

## What is implemented

- Actual Firebase Auth createUser/signIn/signOut calls, an Auth state listener,
  restoration loading, safe errors, and authenticated/signed-out navigation.
  Demo success alerts and artificial registration delays are removed.
- Missing Firebase client configuration produces a setup screen, not a fake login.
- Auth success and profile provisioning are separate: failed profile saves retain
  the authenticated account and offer profile recovery. Registration is never
  repeated automatically. Restoration only reads; it never creates profiles or
  default settings.
- Firestore server reads for paged players, teams, matches, details, events,
  metadata-only highlights and the current user's data. Pages have 20 results plus
  one lookahead document; source queries conform to the draft rule limits.
- Accent-insensitive search over loaded pages, with explicit load-more controls.
  No global substring search or verified roster/statistics data is invented.
- Existing competition_mappings.json is bundled directly and reused. Match joins
  validate team IDs and reviewed provider/internal competition identities.
- Private profile/settings/favorite/watchlist changes use owned-document
  transactions, explicit user actions, server timestamps, conflict checks and
  read-back. Desired saved state is idempotent; stale targets can be removed.
- UID/session generation checks reject stale async responses. Sign-out clears
  private state; transaction callbacks recheck the current Auth UID. Firestore uses
  memory-only caching and server reads, avoiding persistent provider/private data.
- No video URLs, downloads or playback. The replay layout shows metadata markers
  and a video-unavailable state. Unknown durations/scores remain unavailable.

The media/provenance restrictions remain in force. Real feeds query isDemo=false.
If an explicitly saved demo record is opened, details/analysis/timeline display a
fictional-data banner. No fallback sample matches are inserted into real feeds.

## Exact Mac setup

1. Transfer this commit to the Mac checkout. It has not been pushed automatically;
   push it yourself or transfer the working checkout, then pull on the Mac.
2. Install **Xcode 26.2 or later** and an iOS Simulator runtime. The project pins
   Firebase Apple SDK **13.2.0**, which requires the modern Xcode toolchain. The app
   deployment target remains iOS 17. See the official
   [Firebase setup](https://firebase.google.com/docs/ios/setup) and
   [SDK release notes](https://firebase.google.com/support/release-notes/ios).
3. Open the existing project from the repository root:

~~~sh
open MatchLens.xcodeproj
~~~

4. Let Xcode resolve the existing Firebase package reference. It already links
   FirebaseCore, FirebaseAuth and FirebaseFirestore; do not add a duplicate package.
   Package resolution was not performed on Windows.
5. In Firebase Console, use the existing MatchLens project. Confirm/register its
   **Apple iOS app** with the exact bundle identifier used by the target. The current
   placeholder is com.example.MatchLens. If the Firebase app uses another identifier,
   change the target's identifier to that registered value; do not guess.
6. Download that iOS app's **GoogleService-Info.plist**. Copy it into MatchLensApp/
   first, then use Xcode **File > Add Files to MatchLens**, select it, and check
   **Add to targets: MatchLens**. Verify its target membership / Copy Bundle Resources.
   Keep its filename unchanged. It is ignored by Git in this checkout.
   This is an iOS client configuration, never the Admin service-account JSON.
   No dummy configuration or real API key is included in source control.
7. Confirm **Authentication > Sign-in method > Email/Password** is enabled.
   Bootstrap checks that the plist bundle ID matches the running app.
8. Review/audit the Firestore access policy below **before testing any write**.
   Use the emulator security tests before manually deploying any reviewed rules.
9. Select the **MatchLens** scheme and an installed **iPhone simulator**, then
   press Command-R. For a physical device, select the appropriate development
   team under Signing & Capabilities. Do not use My Mac.

The app delegate configures Firebase once. The target disables delegate swizzling
for this SwiftUI Email/Password flow. No Analytics, Messaging, Storage, Admin SDK
or football-provider key is added to the iOS target.

## Rules for inspection: no deployment performed

Firebase/firestore.rules already describes the schema used by the native client;
no new permission expansion is necessary:

- Signed-in users may read curated catalog collections using bounded queries.
  Client writes to players/teams/competitions/matches/events/highlights are denied.
- Only request.auth.uid may access users/{uid} and its settings/favorites/watchlist.
- Exact private fields and schemaVersion=1 are required. Profiles use uid,
  displayName, createdAt and updatedAt; email/password remain Firebase Auth data.
- Server timestamps are required for create/update. createdAt/UID cannot be
  overwritten by profile edits. Favorite/watchlist records are immutable except
  for owner removal, with canonical IDs and existing public targets.
- Highlight reads require unconfirmed rights and null media references. The client
  requests those same filters and never enables actual media playback.

**These rules remain a draft.** The Firebase emulator assertions were not run here.
Follow the optional loopback-only commands in
[the backend integration contract](IOS_BACKEND_INTEGRATION.md#draft-firebase-rules-and-tests).
Review the index file too. No deploy command was executed.

Rules do not redact fields: audit existing public documents for private/provider
extras before exposing them to a client. The app constructs only the allowed DTOs,
but the SDK still receives full documents. Admin ingestion/reuse permissions must
be reviewed independently. The initial confirmed cloud dataset contains five
players and five teams; real competition/match availability was not inspected.
Empty feeds and permission errors are shown honestly.

## Manual functional test checklist

Do these checks after reviewing/deploying the appropriate rules yourself:

1. Missing/mismatched plist: setup message, no simulated authentication.
2. Invalid forms and incorrect password: clear errors; no navigation to Home.
3. Registration: a real Auth user plus owned profile are created only after the
   Create Account action. Never use this as a read-only test. If profile writing
   fails, retry profile recovery; do not create the same account again.
4. Sign-in, app relaunch/session restoration, sign-out, and account switching.
   Check that no previous user's profile/settings/saved items appear.
5. Player/team search, pagination, detail fields and source attribution; failed
   network/rule reads must not become fake empty successes.
6. Published match details: UTC kickoff, nullable scores and separate regulation/
   extra-time/shootout values. No invented statistics or player club membership.
7. Save/remove a player, team, match, metadata highlight and match watchlist entry.
   Confirm read-back, no duplicates and successful removal of a stale target.
8. Change display name/settings. Use a second device/client to change settings
   between read/save: stale edits must conflict rather than overwrite.
9. Use a second Auth user to verify private data access is denied. Python/Admin
   reads cannot demonstrate client security because Admin bypasses these rules.
10. Highlight markers remain metadata-only; there must be no video download/playback.
    Verify VoiceOver, keyboard, landscape, small iPhones and light/dark appearance.

Push notification delivery, account deletion, verified lineups/statistics, licensed
media and expanded approved data are outside this batch.

## Executed checks and pending native build

- Full Python suite: **298 tests, OK**.
- All **19 app Swift files**: syntax parsing passed. This does not type-check
  SwiftUI or Firebase against an Apple SDK.
- Client model executable: **79 assertions passed**, using local schema fixtures.
- Project structure executable: **56 assertions passed**, including property-list
  parsing, source/resource membership, one app entry and SDK product wiring.
- Existing authentication validation: **23 cases passed**.
- Existing replay arithmetic: **23 assertions passed**.
- Xcode build, simulator/device tests, package resolution and live Firebase
  Auth/Firestore/rule tests: **NOT EXECUTED**.

On the Mac:

~~~sh
xcodebuild -list -project MatchLens.xcodeproj
xcodebuild -resolvePackageDependencies -project MatchLens.xcodeproj -scheme MatchLens
xcodebuild -showdestinations -project MatchLens.xcodeproj -scheme MatchLens
xcodebuild -project MatchLens.xcodeproj -scheme MatchLens -configuration Debug \
  -destination 'generic/platform=iOS Simulator' -derivedDataPath .build/xcode \
  CODE_SIGNING_ALLOWED=NO build
~~~

The last command compiles without launching. Run manually with Command-R on a
specific simulator to test the configured app. If it fails, treat the source
integration as pending and fix the reported native errors before calling it complete.

Foundation-only checks from the repository root:

~~~sh
swiftc -parse-as-library MatchLensApp/Data/ClientModels.swift Tests/ClientModelTests.swift \
  -o /tmp/matchlens-client-tests && /tmp/matchlens-client-tests
swiftc -parse-as-library Tests/ProjectStructureTests.swift \
  -o /tmp/matchlens-project-tests && /tmp/matchlens-project-tests
python -B -m unittest discover -s Backend -p "test_*.py" -q
~~~

No generated executables, SDK checkouts, private credentials or provider response
datasets are part of the commit. Existing Python 3.10 Google-library support
warnings remain an environment issue; the backend suite still passes.
