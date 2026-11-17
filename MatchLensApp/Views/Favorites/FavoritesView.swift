import SwiftUI

struct FavoritesView: View {
    @State private var selectedSection: SavedSection = .matches
    @State private var savedItems = SavedFavorite.samples
    @State private var activeSheet: FavoritesDestination?

    var body: some View {
        NavigationStack {
            ZStack {
                FavoritesStyle.background.ignoresSafeArea()
                ScrollView {
                    VStack(alignment: .leading, spacing: 0) {
                        Text("Saved Moments")
                            .font(.system(size: 28, weight: .bold))
                            .accessibilityAddTraits(.isHeader)
                        Text("Your personalized match collection")
                            .font(.system(size: 13))
                            .foregroundColor(FavoritesStyle.secondary)
                            .padding(.top, 8)

                        sectionPicker
                            .padding(.top, 30)
                            .padding(.bottom, 20)

                        if savedItems.isEmpty {
                            VStack(alignment: .leading, spacing: 8) {
                                Text(selectedSection == .matches ? "No saved matches yet" : "No saved moments yet")
                                    .font(.headline)
                                Text("Your bookmarked highlights will appear here.")
                                    .font(.subheadline)
                                    .foregroundColor(FavoritesStyle.secondary)
                            }
                            .padding(20)
                            .frame(maxWidth: .infinity, minHeight: 140, alignment: .leading)
                            .background(FavoritesStyle.card)
                            .clipShape(RoundedRectangle(cornerRadius: 22))
                        } else {
                            VStack(spacing: 14) {
                                ForEach(savedItems) { item in
                                    NavigationLink {
                                        matchDetails(item)
                                    } label: {
                                        savedCard(item)
                                    }
                                    .buttonStyle(.plain)
                                    .contextMenu {
                                        Button(role: .destructive) {
                                            remove(item)
                                        } label: {
                                            Label("Remove from Saved", systemImage: "bookmark.slash")
                                        }
                                    }
                                    .accessibilityHint("Opens details. Long press for removal options.")
                                    .accessibilityAction(named: Text("Remove from Saved")) {
                                        remove(item)
                                    }
                                }
                            }
                        }

                        Text("Bookmark favorite moments")
                            .font(.system(size: 19, weight: .bold))
                            .accessibilityAddTraits(.isHeader)
                            .padding(.top, 44)
                        Text("Replay exactly what you loved.")
                            .font(.system(size: 13))
                            .foregroundColor(FavoritesStyle.secondary)
                            .padding(.top, 10)

                        HStack(spacing: 10) {
                            Image(systemName: "star")
                                .accessibilityHidden(true)
                            Text("Your collection stays in sync")
                        }
                        .font(.system(size: 14))
                        .foregroundColor(FavoritesStyle.secondary)
                        .padding(.horizontal, 18)
                        .frame(maxWidth: .infinity, minHeight: 94, alignment: .leading)
                        .background(FavoritesStyle.card)
                        .clipShape(RoundedRectangle(cornerRadius: 20))
                        .padding(.top, 22)
                    }
                    .foregroundColor(FavoritesStyle.primary)
                    .frame(maxWidth: 440, alignment: .leading)
                    .padding(.horizontal, 22)
                    .padding(.top, 30)
                    .padding(.bottom, 28)
                    .frame(maxWidth: .infinity)
                }
            }
            .safeAreaInset(edge: .bottom, spacing: 0) { bottomNavigation }
            .toolbar(.hidden, for: .navigationBar)
        }
        .tint(FavoritesStyle.blue)
        .preferredColorScheme(.dark)
        .sheet(item: $activeSheet) { destination in
            switch destination {
            case .home:
                // These screens own their bars; only their bar is shown in the sheet.
                HomeView()
            case .profile:
                ProfileView()
            case .matches:
                NavigationStack {
                    ZStack {
                        FavoritesStyle.background.ignoresSafeArea()
                        Text("Placeholder — the Matches screen will be added here.")
                            .foregroundColor(FavoritesStyle.secondary)
                            .padding(24)
                    }
                    .navigationTitle("Matches")
                    .navigationBarTitleDisplayMode(.inline)
                    .toolbar {
                        ToolbarItem(placement: .confirmationAction) {
                            Button("Done") { activeSheet = nil }
                        }
                    }
                }
            }
        }
    }

    private var sectionPicker: some View {
        HStack(spacing: 10) {
            ForEach(SavedSection.allCases) { section in
                Button {
                    selectedSection = section
                } label: {
                    Text(section.rawValue)
                        .font(.system(size: 12, weight: .bold))
                        .foregroundColor(selectedSection == section ? .white : FavoritesStyle.secondary)
                        .frame(width: 94, height: 30)
                        .background(selectedSection == section ? FavoritesStyle.blue : FavoritesStyle.thumbnail)
                        .clipShape(Capsule())
                        .frame(minHeight: 44)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityAddTraits(selectedSection == section ? .isSelected : [])
            }
        }
        // The visual pills are 30 points tall, with 44-point touch targets.
        .padding(.vertical, -7)
    }

    private func savedCard(_ item: SavedFavorite) -> some View {
        HStack(spacing: 12) {
            ZStack(alignment: .top) {
                RoundedRectangle(cornerRadius: 14)
                    .fill(FavoritesStyle.thumbnail)
                FavoritesStyle.blue
                    .frame(height: 6)
                    .clipShape(Capsule())
                Image(systemName: "star.fill")
                    .font(.system(size: 20))
                    .foregroundColor(FavoritesStyle.lime)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .accessibilityHidden(true)
            }
            .frame(width: 110, height: 84)

            VStack(alignment: .leading, spacing: 10) {
                Text(selectedSection == .matches ? item.match : item.moment)
                    .font(.system(size: 14, weight: .bold))
                Text(selectedSection == .matches ? "\(item.moment) • \(item.time)" : "\(item.match) • \(item.time)")
                    .font(.system(size: 11))
                    .foregroundColor(FavoritesStyle.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(FavoritesStyle.card)
        .clipShape(RoundedRectangle(cornerRadius: 22))
        .overlay {
            RoundedRectangle(cornerRadius: 22)
                .stroke(item.outlined ? Color(red: 0, green: 0.62, blue: 1) : .clear, lineWidth: 2.5)
        }
        .contentShape(RoundedRectangle(cornerRadius: 22))
    }

    private var bottomNavigation: some View {
        HStack(spacing: 4) {
            navigationButton("Home", destination: .home)
            navigationButton("Matches", destination: .matches)
            Button { selectedSection = .matches } label: {
                Text("Saved")
                    .font(.system(size: 11, weight: .bold))
                    .foregroundColor(.white)
                    .frame(maxWidth: .infinity, minHeight: 44)
                    .background(Color(red: 39 / 255, green: 69 / 255, blue: 119 / 255))
                    .clipShape(Capsule())
            }
            .accessibilityAddTraits(.isSelected)
            navigationButton("Profile", destination: .profile)
        }
        .buttonStyle(.plain)
        .padding(5)
        .padding(.vertical, 4)
        .background(Color(red: 39 / 255, green: 48 / 255, blue: 65 / 255))
        .clipShape(RoundedRectangle(cornerRadius: 27))
        .overlay {
            RoundedRectangle(cornerRadius: 27)
                .stroke(FavoritesStyle.secondary.opacity(0.45), lineWidth: 1)
        }
        .frame(maxWidth: 450)
        .padding(.horizontal, 18)
        .padding(.bottom, 8)
        .frame(maxWidth: .infinity)
        .background(FavoritesStyle.background)
    }

    private func navigationButton(_ title: String, destination: FavoritesDestination) -> some View {
        Button { activeSheet = destination } label: {
            Text(title)
                .font(.system(size: 11))
                .foregroundColor(FavoritesStyle.secondary)
                .frame(maxWidth: .infinity, minHeight: 44)
                .contentShape(Rectangle())
        }
    }

    private func matchDetails(_ item: SavedFavorite) -> some View {
        ZStack {
            FavoritesStyle.background.ignoresSafeArea()
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    Text(item.match).font(.title2.bold())
                    Text("\(item.moment) • \(item.time)")
                    Text("Placeholder — match details and playback will be added later.")
                    Text("Saved items are held in memory for this demo. Cloud sync is not connected.")
                        .font(.footnote)
                }
                .foregroundColor(FavoritesStyle.primary)
                .padding(24)
                .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
        .navigationTitle("Match Details")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar(.visible, for: .navigationBar)
    }

    private func remove(_ item: SavedFavorite) {
        withAnimation {
            savedItems.removeAll { $0.id == item.id }
        }
    }
}

private enum SavedSection: String, CaseIterable, Identifiable {
    case matches = "Matches"
    case moments = "Moments"
    var id: String { rawValue }
}

private enum FavoritesDestination: String, Identifiable {
    case home, matches, profile
    var id: String { rawValue }
}

// Each sample represents a bookmarked moment associated with a match.
private struct SavedFavorite: Identifiable {
    let id: String
    let match: String
    let moment: String
    let time: String
    let outlined: Bool

    static let samples = [
        SavedFavorite(id: "winning-goal", match: "City Blues vs Reds", moment: "Winning goal", time: "10:16", outlined: false),
        SavedFavorite(id: "great-save", match: "North FC vs West", moment: "Great save", time: "04:38", outlined: true)
    ]
}

private enum FavoritesStyle {
    static let background = Color(red: 12 / 255, green: 16 / 255, blue: 32 / 255)
    static let card = Color(red: 26 / 255, green: 38 / 255, blue: 61 / 255)
    static let thumbnail = Color(red: 30 / 255, green: 48 / 255, blue: 76 / 255)
    static let primary = Color(red: 240 / 255, green: 243 / 255, blue: 251 / 255)
    static let secondary = Color(red: 166 / 255, green: 185 / 255, blue: 209 / 255)
    static let blue = Color(red: 40 / 255, green: 120 / 255, blue: 240 / 255)
    static let lime = Color(red: 166 / 255, green: 1, blue: 0)
}

#Preview {
    FavoritesView()
}
