import SwiftUI

struct ProfileView: View {
    @EnvironmentObject private var app: AppStore
    @State private var activeSheet: ProfileSheet?
    @State private var showLogoutConfirmation = false
    private var favoriteTeamName: String {
        guard let id = app.preferences.favoriteTeamId else { return "No favorite team" }
        return app.teams.first { $0.id == id }?.name ?? id
    }
    private var notificationSummary: String {
        if app.preferences.highlightNotifications && app.preferences.scoreNotifications { return "Highlights and scores" }
        if app.preferences.highlightNotifications { return "Highlights only" }
        return app.preferences.scoreNotifications ? "Scores only" : "Notifications off"
    }
    var body: some View {
        ZStack {
            MatchLensStyle.background.ignoresSafeArea()
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    Text("My Profile").font(.title.bold()).accessibilityAddTraits(.isHeader)
                    AdaptiveActionRow {
                        Text("ML").font(.system(size: 24, weight: .bold)).foregroundStyle(.white)
                            .frame(width: 70, height: 70).background(MatchLensStyle.blue).clipShape(Circle())
                            .accessibilityHidden(true)
                        VStack(alignment: .leading, spacing: 8) {
                            Text(app.profile?.displayName ?? "Profile unavailable").font(.headline)
                            Text(app.email).font(.footnote).foregroundStyle(MatchLensStyle.secondary)
                        }
                    }.padding(.vertical, 20)
                    preferenceCard("Display name", subtitle: app.profile?.displayName ?? "", sheet: .name)
                    Text("Preferences").font(.title2.bold()).accessibilityAddTraits(.isHeader).padding(.top, 18)
                    preferenceCard("Favorite team", subtitle: favoriteTeamName, sheet: .team)
                    preferenceCard("Notifications", subtitle: notificationSummary, sheet: .notifications)
                    preferenceCard("Appearance", subtitle: app.preferences.appearance.capitalized, sheet: .appearance)
                    preferenceCard("About MatchLens", subtitle: "Version 1.0", sheet: .about)
                    if let error = app.errorMessage { Text(error).foregroundStyle(.red) }
                    Button("Log out →", role: .destructive) { showLogoutConfirmation = true }
                        .frame(minHeight: 44).disabled(app.authBusy || app.saving)
                }
                .foregroundStyle(MatchLensStyle.primary).frame(maxWidth: 440, alignment: .leading)
                .padding(22).frame(maxWidth: .infinity)
            }
        }
        .toolbar(.hidden, for: .navigationBar)
        .sheet(item: $activeSheet) { sheet in
            if sheet == .name { ProfileNameEditor(current: app.profile?.displayName ?? "") }
            else if sheet == .about {
                NavigationStack {
                    Form { Text("MatchLens"); Text("Football highlights and match analysis."); Text("Version 1.0") }
                        .navigationTitle("About MatchLens")
                        .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { activeSheet = nil } } }
                }
            } else { PreferencesEditor(current: app.preferences, section: sheet) }
        }
        .alert("Log out?", isPresented: $showLogoutConfirmation) {
            Button("Cancel", role: .cancel) {}
            Button("Log out", role: .destructive) { app.signOut() }
        } message: { Text("Sign out of MatchLens on this device?") }
        .task { await app.loadTeams() }
    }
    private func preferenceCard(_ title: String, subtitle: String, sheet: ProfileSheet) -> some View {
        Button { app.mutationMessage = nil; activeSheet = sheet } label: {
            VStack(alignment: .leading, spacing: 7) {
                Text(title).font(.subheadline.bold())
                Text(subtitle).font(.footnote).foregroundStyle(MatchLensStyle.secondary)
            }
            .padding(.horizontal, 16).padding(.vertical, 13).frame(maxWidth: .infinity, minHeight: 66, alignment: .leading)
            .background(MatchLensStyle.card).clipShape(RoundedRectangle(cornerRadius: 18))
        }.buttonStyle(.plain)
    }
}
private enum ProfileSheet: String, Identifiable {
    case name = "Display name", team = "Favorite team", notifications = "Notifications", appearance = "Appearance", about = "About MatchLens"
    var id: String { rawValue }
}
private struct ProfileNameEditor: View {
    @EnvironmentObject private var app: AppStore
    @Environment(\.dismiss) private var dismiss
    @State private var name: String
    init(current: String) { _name = State(initialValue: current) }
    var body: some View {
        NavigationStack {
            Form {
                TextField("Display name", text: $name).textContentType(.name)
                if let error = app.mutationMessage { Text(error).foregroundStyle(.red) }
                if app.saving { ProgressView("Updating profile…") }
                Button("Save") {
                    Task { if await app.updateProfile(name: name.trimmingCharacters(in: .whitespacesAndNewlines)) { dismiss() } }
                }.disabled(app.saving)
                Button("Reload current name") {
                    Task { if await app.reloadPrivate(), let profile = app.profile { name = profile.displayName } }
                }.disabled(app.saving)
            }
            .navigationTitle("Display name").navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() }.disabled(app.saving) } }
        }
        .interactiveDismissDisabled(app.saving)
    }
}
private struct PreferencesEditor: View {
    @EnvironmentObject private var app: AppStore
    @Environment(\.dismiss) private var dismiss
    @State private var draft: UserPreferences
    let section: ProfileSheet
    init(current: UserPreferences, section: ProfileSheet) { _draft = State(initialValue: current); self.section = section }
    var body: some View {
        NavigationStack {
            Form {
                switch section {
                case .team:
                    Picker("Favorite team", selection: $draft.favoriteTeamId) {
                        Text("None").tag(Optional<String>.none)
                        if let id = draft.favoriteTeamId, !app.teams.contains(where: { $0.id == id }) {
                            Text("Current team: \(id)").tag(Optional(id))
                        }
                        ForEach(app.teams) { team in Text(team.name).tag(Optional(team.id)) }
                    }
                    if app.teamsCursor != nil { Button("Load more teams") { Task { await app.loadTeams(more: true) } } }
                    if app.teamsLoading && app.teams.isEmpty { ProgressView("Loading teams…") }
                    if let error = app.teamsError { Text(error).foregroundStyle(.red); Button("Retry teams") { Task { await app.loadTeams(reset: true) } } }
                case .notifications:
                    Toggle("Highlights", isOn: $draft.highlightNotifications)
                    Toggle("Scores", isOn: $draft.scoreNotifications)
                    Text("Preferences only. Push notification delivery is not configured.").font(.caption)
                case .appearance:
                    Picker("Appearance", selection: $draft.appearance) {
                        Text("System").tag("system"); Text("Dark").tag("dark"); Text("Light").tag("light")
                    }.pickerStyle(.inline)
                default: EmptyView()
                }
                if let error = app.mutationMessage { Text(error).foregroundStyle(.red) }
                if app.saving { ProgressView("Updating preferences…") }
                Button("Save settings") { Task { if await app.savePreferences(draft) { dismiss() } } }.disabled(app.saving)
                Button("Reload current settings") {
                    Task { if await app.reloadPrivate() { draft = app.preferences } }
                }.disabled(app.saving)
            }
            .navigationTitle(section.rawValue).navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() }.disabled(app.saving) } }
        }
        .task { if section == .team { await app.loadTeams() } }
        .interactiveDismissDisabled(app.saving)
    }
}
#Preview { ProfileView().environmentObject(AppStore()) }
