import SwiftUI

// Include this file in the iOS app target as its only @main entry point.
@main
@MainActor
struct MatchLensApp: App {
    @UIApplicationDelegateAdaptor(MatchLensAppDelegate.self) private var delegate
    @StateObject private var app = AppStore()
    var body: some Scene {
        WindowGroup {
            AppRootView()
                .environmentObject(app)
        }
    }
}
