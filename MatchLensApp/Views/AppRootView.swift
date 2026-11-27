import SwiftUI

struct AppRootView: View {
    @EnvironmentObject private var app: AppStore
    var body: some View {
        Group {
            switch app.phase {
            case .restoring:
                ZStack {
                    MatchLensStyle.background.ignoresSafeArea()
                    VStack(spacing: 20) {
                        LoadingCard(title: "Restoring your session…")
                        if app.uid != nil {
                            Button("Sign out") { app.signOut() }.disabled(app.authBusy || app.saving)
                        }
                    }.padding(22).frame(maxWidth: 480)
                }
            case .signedOut: LoginView()
            case .ready: SignedInTabs().id(app.sessionKey)
            case .profileRequired, .profileError: ProfileRecoveryView().id(app.sessionKey)
            case .configurationRequired:
                ZStack {
                    MatchLensStyle.background.ignoresSafeArea()
                    DataNotice(title: "Firebase setup required", message: app.errorMessage ?? "Follow Docs/NATIVE_FIREBASE_SETUP.md.")
                        .padding(24)
                }
            }
        }
        .preferredColorScheme(app.preferences.appearance == "system" ? nil : (app.preferences.appearance == "light" ? .light : .dark))
        .task { app.start() }
    }
}
private struct SignedInTabs: View {
    @EnvironmentObject private var app: AppStore
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    var body: some View {
        TabView(selection: $app.tab) {
            HomeView().tag(AppTab.home)
            MatchLibraryView().tag(AppTab.matches)
            FavoritesView().tag(AppTab.saved)
            NavigationStack { ProfileView() }.tag(AppTab.profile)
        }
        .toolbar(.hidden, for: .tabBar)
        .safeAreaInset(edge: .bottom, spacing: 0) {
            LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 4),
                                    count: dynamicTypeSize.isAccessibilitySize ? 2 : 4), spacing: 4) {
                ForEach(AppTab.allCases, id: \.self) { tab in
                    Button { app.tab = tab } label: {
                        Text(tab.rawValue).font(.caption.weight(app.tab == tab ? .bold : .regular))
                            .foregroundStyle(app.tab == tab ? .white : Color(red: 166 / 255, green: 185 / 255, blue: 209 / 255))
                            .multilineTextAlignment(.center)
                            .frame(maxWidth: .infinity, minHeight: 44)
                            .background(app.tab == tab ? MatchLensStyle.blue.opacity(0.35) : .clear)
                            .clipShape(Capsule())
                    }
                    .accessibilityAddTraits(app.tab == tab ? .isSelected : [])
                }
            }
            .buttonStyle(.plain).padding(5).padding(.vertical, 4)
            .background(Color(red: 39 / 255, green: 48 / 255, blue: 65 / 255))
            .clipShape(RoundedRectangle(cornerRadius: 27))
            .overlay { RoundedRectangle(cornerRadius: 27).stroke(MatchLensStyle.secondary.opacity(0.45)) }
            .frame(maxWidth: 450).padding(.horizontal, 18).padding(.bottom, 8)
            .frame(maxWidth: .infinity).background(MatchLensStyle.background)
        }
        .tint(MatchLensStyle.blue)
    }
}
private struct ProfileRecoveryView: View {
    @EnvironmentObject private var app: AppStore
    @State private var name = ""
    var body: some View {
        NavigationStack {
            Form {
                Section("Signed in") { Text(app.email) }
                if app.phase == .profileRequired {
                    Section("Complete your profile") {
                        TextField("Display name", text: $name).textContentType(.name)
                        Button("Save profile") { Task { await app.completeProfile(name: name.trimmingCharacters(in: .whitespacesAndNewlines)) } }
                            .disabled(app.authBusy)
                    }
                }
                if let error = app.errorMessage { Text(error).foregroundStyle(.red).accessibilityLabel("Profile error: \(error)") }
                if app.authBusy { ProgressView("Saving profile…") }
                Button("Retry profile read") { app.retryProfile() }.disabled(app.authBusy)
                Button("Sign out", role: .destructive) { app.signOut() }.disabled(app.authBusy)
            }
            .navigationTitle("MatchLens profile")
            .onAppear { name = app.suggestedName }
        }
    }
}
