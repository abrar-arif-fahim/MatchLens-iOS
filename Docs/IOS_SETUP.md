# Opening MatchLens as an iOS app

The repository previously contained Swift source files without an Xcode project.
Opening a folder or a `.swift` file does not supply an iOS application target.
`MatchLens.xcodeproj` now defines that target and a shared `MatchLens` run scheme.

The target uses the iPhone/iPad device and simulator platforms, with iOS 17.0 as
the minimum deployment version. The Firebase integration now requires Xcode 26.2 or later on a Mac, with an installed
iOS Simulator runtime at or above iOS 17. Newer compatible runtimes also work;
there is no need to install iOS 17 specifically. Mac Catalyst and running the iOS
app as a Mac app are disabled in this target.

## Run in an iPhone simulator

1. Make sure these new project files are present in your Mac checkout alongside
   the existing `MatchLensApp` directory.
2. Close any unrelated or previously created macOS project. From the repository
   root in your Mac Terminal, run:

   ```sh
   open MatchLens.xcodeproj
   ```

3. Select the **MatchLens** scheme in Xcode's toolbar.
4. Choose an installed **iPhone simulator** as the run destination. The runtime
   must be iOS 17 or later. If none is available, install an iOS runtime in
   **Xcode > Settings > Components** (called **Platforms** in some versions).
   Create a simulator in **Window > Devices and Simulators > Simulators** if
   necessary. A generic **Any iOS Device** destination is for building, not
   launching the simulator.
5. Press **Command-R**. The app entry point restores the Firebase session or opens `LoginView`; its Sign up link
   opens `RegisterView`. Both forms retain local validation and now call the Firebase SDK; see the setup requirements below.

The project includes all app Swift files, including `RegisterView.swift`,
`AuthenticationValidation.swift` and `ReplayTimeline.swift`. It excludes the
standalone executables under `Tests/`, which have separate `@main` declarations.
Backend scripts, `.env` and Firebase Admin credentials are not app resources.

## Confirm the project configuration

Select the blue **MatchLens** project in the navigator, then **Targets > MatchLens**.
Both Debug and Release configurations specify:

| Setting | Value |
| --- | --- |
| Base SDK | iOS (`iphoneos`) |
| Supported Platforms | `iphoneos iphonesimulator` |
| iOS Deployment Target | `17.0` |
| Targeted Device Family | iPhone and iPad (`1,2`) |
| Supports Mac Catalyst | No |
| Supports Mac Designed for iPhone/iPad | No |

If **My Mac** is still the only destination, first check that the open project
and selected scheme are both **MatchLens**, then check the installed iOS runtime.
Do not remove `.keyboardType(.emailAddress)`; it is valid for this iOS target.

The bundle identifier `com.example.MatchLens` is a development placeholder. For
a physical iPhone, choose your Apple development team under **Signing &
Capabilities**, enable automatic signing, and replace the placeholder with a
unique identifier for your project. The simulator does not require device
provisioning. No team identifier or private signing material is stored here.
An application icon and release/distribution setup remain future work.

## Build checks on the Mac

From the repository root:

```sh
xcodebuild -list -project MatchLens.xcodeproj
xcodebuild -showdestinations -project MatchLens.xcodeproj -scheme MatchLens
xcodebuild -project MatchLens.xcodeproj -scheme MatchLens -configuration Debug \
  -destination 'generic/platform=iOS Simulator' -derivedDataPath .build/xcode \
  CODE_SIGNING_ALLOWED=NO build
```

The last command builds for the simulator but does not launch it. Use Command-R
with a specific iPhone simulator selected to launch the app. `.build/` is already
ignored by Git.

Project structure and source references can be checked on Windows, but a full
iOS build and simulator test require the Mac's Xcode tools and iOS SDK.

## Swift review and local checks — 22 November 2026

All app and standalone-test Swift files were reviewed. The registration screen's
updated layout is preserved. Its missing password-visibility/loading state was
restored, input focus and keyboard submission were reconnected, and its demo
delay now uses a view-bound task. Returning to Login clears the loading state;
cancelled work cannot display the completion alert. This follows Apple's
[view-task lifecycle guidance](https://developer.apple.com/videos/play/wwdc2023/10248/).
At that earlier review, registration created no account. The current source now calls Firebase Auth; live verification remains pending.

Both forms use `AuthenticationValidation.swift` for the same local email-format
check. This rejects empty domain labels, leading/trailing local dots, repeated
local dots and domain labels with invalid hyphen placement. It does not verify
mailbox ownership or replace future service-side validation.

Executed on Windows: all **11 app Swift files** passed syntax parsing; the
standalone authentication executable passed **23 email cases**; the replay
executable passed **23 timing assertions**. The project property list parsed
successfully. These checks do not type-check SwiftUI against the iOS SDK or test
keyboard/navigation behavior on a running simulator.

To repeat the standalone checks on your Mac, from the repository root:

```sh
swiftc -parse-as-library MatchLensApp/Views/Authentication/AuthenticationValidation.swift \
  Tests/AuthenticationValidationTests.swift -o /tmp/matchlens-auth-tests && /tmp/matchlens-auth-tests
swiftc -parse-as-library MatchLensApp/Views/Replay/ReplayTimeline.swift \
  Tests/ReplayTimelineTests.swift -o /tmp/matchlens-replay-tests && /tmp/matchlens-replay-tests
```

In the iPhone simulator, check empty/invalid login input; all registration
validation errors; Next/Done keyboard actions; both password visibility buttons;
and returning to Login while the registration spinner is visible. Returning and
reopening must not show an old success alert. Also check library search/filters,
the selected replay title, timeline controls and removal of saved demo items.

The app still starts at Login with local demo validation. It does not navigate
into Home after signing in. Several Home/Profile/Saved destinations remain
explicit placeholders, preferences/favorites are temporary, and no replay video
is bundled. Other screens can be examined through their individual Xcode
previews until that navigation/integration work is implemented.

Apple references:
[Create an Xcode project](https://developer.apple.com/documentation/xcode/creating-an-xcode-project-for-an-app),
[build settings](https://developer.apple.com/documentation/xcode/build-settings-reference),
[run on a simulator or device](https://developer.apple.com/documentation/xcode/building-and-running-an-app).

## Native Firebase source integration

See [Native Firebase setup](NATIVE_FIREBASE_SETUP.md) before running the current app.
The target now pins Firebase SDK 13.2.0, links its three required products and
includes the native data/session services. Add the correct iOS client plist to
the target on the Mac; the source does not include credentials or a dummy config.
The earlier validation-only review above is historical. Native SDK compilation,
live authentication, owned writes and simulator/device validation are still pending.
