import SwiftUI

// Include this file in the iOS app target as its only @main entry point.
@main
struct MatchLensApp: App {
    var body: some Scene {
        WindowGroup {
            // LoginView owns the NavigationStack used to open RegisterView.
            LoginView()
                .preferredColorScheme(.dark)
        }
    }
}
