import SwiftUI

struct ProfileView: View {
    @State private var favoriteTeam = "City Blues"
    @State private var highlightNotifications = true
    @State private var scoreNotifications = true
    @State private var darkMode = true
    @State private var activeSheet: ProfileSheet?
    @State private var showLogoutConfirmation = false

    private let teams = ["City Blues", "United Reds", "North London", "Royal Whites"]
    private let blue = Color(red: 34 / 255, green: 92 / 255, blue: 196 / 255)

    private var background: Color {
        darkMode ? Color(red: 12 / 255, green: 16 / 255, blue: 32 / 255) : Color(red: 0.95, green: 0.96, blue: 0.98)
    }

    private var cardColor: Color {
        darkMode ? Color(red: 26 / 255, green: 38 / 255, blue: 61 / 255) : .white
    }

    private var primaryText: Color { darkMode ? Color(red: 240 / 255, green: 243 / 255, blue: 251 / 255) : .black }
    private var secondaryText: Color {
        darkMode ? Color(red: 166 / 255, green: 185 / 255, blue: 209 / 255) : Color(red: 0.32, green: 0.39, blue: 0.48)
    }

    private var notificationSummary: String {
        if highlightNotifications && scoreNotifications { return "Highlights and scores" }
        if highlightNotifications { return "Highlights only" }
        if scoreNotifications { return "Scores only" }
        return "Notifications off"
    }

    var body: some View {
        ZStack {
            background.ignoresSafeArea()
            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    Text("My Profile")
                        .font(.system(size: 28, weight: .bold))
                        .accessibilityAddTraits(.isHeader)

                    HStack(spacing: 16) {
                        Text("ML")
                            .font(.system(size: 24, weight: .bold))
                            .foregroundColor(.white)
                            .frame(width: 70, height: 70)
                            .background(blue)
                            .clipShape(Circle())
                            .accessibilityLabel("Profile initials ML")

                        VStack(alignment: .leading, spacing: 8) {
                            Text("Football Fan")
                                .font(.system(size: 19, weight: .bold))
                            Text("fan@matchlens.app")
                                .font(.system(size: 13))
                                .foregroundColor(secondaryText)
                        }
                    }
                    .padding(.top, 32)

                    Text("Preferences")
                        .font(.system(size: 20, weight: .bold))
                        .accessibilityAddTraits(.isHeader)
                        .padding(.top, 46)
                        .padding(.bottom, 14)

                    VStack(spacing: 12) {
                        preferenceCard("Favorite team", subtitle: favoriteTeam, sheet: .team)
                        preferenceCard("Notifications", subtitle: notificationSummary, sheet: .notifications)
                        preferenceCard("Appearance", subtitle: darkMode ? "Dark mode" : "Light mode", sheet: .appearance)
                        preferenceCard("About MatchLens", subtitle: "Version 1.0", sheet: .about)
                    }

                    Button {
                        showLogoutConfirmation = true
                    } label: {
                        Text("Log out →")
                            .font(.system(size: 15, weight: .bold))
                            .foregroundColor(Color(red: 1, green: 0.23, blue: 0.18))
                            .frame(minHeight: 44)
                            .padding(.horizontal, 16)
                            .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .padding(.top, 24)
                }
                .foregroundColor(primaryText)
                .frame(maxWidth: 440, alignment: .leading)
                .padding(.horizontal, 22)
                .padding(.top, 30)
                .padding(.bottom, 16)
                .frame(maxWidth: .infinity)
            }
        }
        .safeAreaInset(edge: .bottom, spacing: 0) { bottomNavigation }
        .preferredColorScheme(darkMode ? .dark : .light)
        .tint(blue)
        .toolbar(.hidden, for: .navigationBar)
        .sheet(item: $activeSheet) { sheet in
            if sheet == .home {
                // Home already owns its NavigationStack and bottom bar.
                // Swipe down to return to this profile without nesting tab bars.
                HomeView()
            } else {
                preferenceSheet(sheet)
            }
        }
        .alert("Log out?", isPresented: $showLogoutConfirmation) {
            Button("Cancel", role: .cancel) { }
            Button("Log out", role: .destructive) {
                activeSheet = .logout
            }
        } message: {
            Text("This is a frontend demo. Confirming will not sign out of a real account.")
        }
    }

    private func preferenceCard(_ title: String, subtitle: String, sheet: ProfileSheet) -> some View {
        Button {
            activeSheet = sheet
        } label: {
            VStack(alignment: .leading, spacing: 7) {
                Text(title)
                    .font(.system(size: 14, weight: .bold))
                    .foregroundColor(primaryText)
                Text(subtitle)
                    .font(.system(size: 13))
                    .foregroundColor(secondaryText)
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 13)
            .frame(maxWidth: .infinity, minHeight: 66, alignment: .leading)
            .background(cardColor)
            .clipShape(RoundedRectangle(cornerRadius: 18))
            .contentShape(RoundedRectangle(cornerRadius: 18))
        }
        .buttonStyle(.plain)
    }

    private var bottomNavigation: some View {
        HStack(spacing: 4) {
            tabButton("Home", sheet: .home)
            tabButton("Matches", sheet: .matches)
            tabButton("Saved", sheet: .saved)
            Button {
                // Already on Profile; return to the default profile content.
                activeSheet = nil
            } label: {
                Text("Profile")
                    .font(.system(size: 11, weight: .bold))
                    .foregroundColor(.white)
                    .frame(maxWidth: .infinity, minHeight: 44)
                    .background(Color(red: 39 / 255, green: 69 / 255, blue: 119 / 255))
                    .clipShape(Capsule())
            }
            .accessibilityAddTraits(.isSelected)
        }
        .buttonStyle(.plain)
        .padding(5)
        .padding(.vertical, 4)
        .background(darkMode ? Color(red: 39 / 255, green: 48 / 255, blue: 65 / 255) : .white)
        .clipShape(RoundedRectangle(cornerRadius: 27))
        .overlay {
            RoundedRectangle(cornerRadius: 27)
                .stroke(secondaryText.opacity(0.45), lineWidth: 1)
        }
        .frame(maxWidth: 450)
        .padding(.horizontal, 18)
        .padding(.bottom, 8)
        .frame(maxWidth: .infinity)
        .background(background)
    }

    private func tabButton(_ title: String, sheet: ProfileSheet) -> some View {
        Button { activeSheet = sheet } label: {
            Text(title)
                .font(.system(size: 11))
                .foregroundColor(secondaryText)
                .frame(maxWidth: .infinity, minHeight: 44)
                .contentShape(Rectangle())
        }
    }

    // All preferences are temporary local state. No permissions or backend calls.
    private func preferenceSheet(_ sheet: ProfileSheet) -> some View {
        NavigationStack {
            Form {
                switch sheet {
                case .team:
                    Section("Select a mock team") {
                        Picker("Favorite team", selection: $favoriteTeam) {
                            ForEach(teams, id: \.self) { team in
                                Text(team).tag(team)
                            }
                        }
                        .pickerStyle(.inline)
                    }
                case .notifications:
                    Section {
                        Toggle("Highlights", isOn: $highlightNotifications)
                        Toggle("Scores", isOn: $scoreNotifications)
                    } footer: {
                        Text("Demo preferences only. No notifications are scheduled.")
                    }
                case .appearance:
                    Picker("Appearance", selection: $darkMode) {
                        Text("Dark mode").tag(true)
                        Text("Light mode").tag(false)
                    }
                    .pickerStyle(.inline)
                case .about:
                    Section("MatchLens") {
                        Text("Every moment matters.")
                        Text("Football highlights and match analysis.")
                        LabeledContent("Version", value: "1.0")
                    }
                case .matches, .saved:
                    Text("Placeholder — \(sheet.rawValue) will be implemented later.")
                case .logout:
                    Text("Demo logout confirmed. No account session has been changed.")
                case .home:
                    EmptyView()
                }
            }
            .navigationTitle(sheet.rawValue)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { activeSheet = nil }
                }
            }
        }
        .preferredColorScheme(darkMode ? .dark : .light)
        .tint(blue)
    }
}

private enum ProfileSheet: String, Identifiable {
    case team = "Favorite team"
    case notifications = "Notifications"
    case appearance = "Appearance"
    case about = "About MatchLens"
    case home = "Home"
    case matches = "Matches"
    case saved = "Saved"
    case logout = "Demo logout"

    var id: String { rawValue }
}

#Preview {
    ProfileView()
}
