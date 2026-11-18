# Opening MatchLens as an iOS app

The repository previously contained Swift source files without an Xcode project.
Opening a folder or a `.swift` file does not supply an iOS application target.
`MatchLens.xcodeproj` now defines that target and a shared `MatchLens` run scheme.

The target uses the iPhone/iPad device and simulator platforms, with iOS 17.0 as
the minimum deployment version. Use Xcode 15 or newer on a Mac, with an installed
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
5. Press **Command-R**. The app entry point launches `LoginView`; its Sign up link
   opens `RegisterView`. Both forms still perform local validation only.

The project includes all ten existing app Swift files, including
`RegisterView.swift` and `ReplayTimeline.swift`. It excludes the standalone
`Tests/ReplayTimelineTests.swift` executable and its separate `@main` declaration.
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

Apple references:
[Create an Xcode project](https://developer.apple.com/documentation/xcode/creating-an-xcode-project-for-an-app),
[build settings](https://developer.apple.com/documentation/xcode/build-settings-reference),
[run on a simulator or device](https://developer.apple.com/documentation/xcode/building-and-running-an-app).
