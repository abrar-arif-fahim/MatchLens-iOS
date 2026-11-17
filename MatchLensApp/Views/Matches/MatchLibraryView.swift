import SwiftUI

struct MatchLibraryView: View {
    @State private var searchText = ""
    @State private var selectedFilter: LibraryFilter = .all
    @State private var activeDestination: LibraryDestination?

    private let matches = LibraryMatch.samples

    private var filteredMatches: [LibraryMatch] {
        let query = searchText.trimmingCharacters(in: .whitespacesAndNewlines)
        let results = matches.filter { match in
            let matchesSearch = query.isEmpty || match.title.localizedCaseInsensitiveContains(query)
            let matchesCategory = selectedFilter == .all || selectedFilter == .recent ||
                (selectedFilter == .league && match.category == .league) ||
                (selectedFilter == .cup && match.category == .cup)
            return matchesSearch && matchesCategory
        }
        return selectedFilter == .recent ? results.sorted { $0.date > $1.date } : results
    }

    var body: some View {
        NavigationStack {
            ZStack {
                LibraryStyle.background.ignoresSafeArea()
                ScrollView {
                    VStack(alignment: .leading, spacing: 0) {
                        Text("Match Library")
                            .font(.system(size: 28, weight: .bold))
                            .accessibilityAddTraits(.isHeader)
                        Text("Demo matches • Find your next replay")
                            .font(.system(size: 13))
                            .foregroundColor(LibraryStyle.secondary)
                            .padding(.top, 10)

                        HStack(spacing: 8) {
                            Image(systemName: "magnifyingglass")
                                .font(.system(size: 13))
                                .foregroundColor(LibraryStyle.secondary)
                                .accessibilityHidden(true)
                            TextField("Search teams or matches", text: $searchText,
                                      prompt: Text("Search teams or matches").foregroundColor(LibraryStyle.secondary))
                                .font(.system(size: 14))
                                .textInputAutocapitalization(.never)
                                .autocorrectionDisabled()
                                .submitLabel(.search)
                        }
                        .padding(.horizontal, 16)
                        .frame(minHeight: 46)
                        .background(LibraryStyle.card)
                        .clipShape(RoundedRectangle(cornerRadius: 17))
                        .padding(.top, 20)

                        filterButtons.padding(.top, 10)

                        if filteredMatches.isEmpty {
                            VStack(alignment: .leading, spacing: 8) {
                                Text("No matches found").font(.headline)
                                Text("Try another team name or filter.")
                                    .font(.subheadline)
                                    .foregroundColor(LibraryStyle.secondary)
                            }
                            .padding(20)
                            .frame(maxWidth: .infinity, minHeight: 120, alignment: .leading)
                            .background(LibraryStyle.card)
                            .clipShape(RoundedRectangle(cornerRadius: 22))
                            .padding(.top, 20)
                        } else {
                            VStack(spacing: 14) {
                                ForEach(filteredMatches) { match in
                                    NavigationLink {
                                        MatchReplayView(
                                            duration: Double(match.replayMinutes) * 60,
                                            matchTitle: match.title,
                                            showDemoEvents: match.id == "city-reds"
                                        )
                                    } label: {
                                        matchCard(match)
                                    }
                                    .buttonStyle(.plain)
                                }
                            }
                            .padding(.top, 20)
                        }
                    }
                    .foregroundColor(LibraryStyle.primary)
                    .frame(maxWidth: 440, alignment: .leading)
                    .padding(.horizontal, 22)
                    .padding(.top, 30)
                    .padding(.bottom, 28)
                    .frame(maxWidth: .infinity)
                }
                .scrollDismissesKeyboard(.interactively)
            }
            .safeAreaInset(edge: .bottom, spacing: 0) { bottomNavigation }
            .toolbar(.hidden, for: .navigationBar)
        }
        .preferredColorScheme(.dark)
        .tint(LibraryStyle.blue)
        .sheet(item: $activeDestination) { destination in
            // Existing screens own their bars; the library bar is behind the sheet.
            switch destination {
            case .home: HomeView()
            case .saved: FavoritesView()
            case .profile: ProfileView()
            }
        }
    }

    private var filterButtons: some View {
        HStack(spacing: 8) {
            ForEach(LibraryFilter.allCases) { filter in
                Button { selectedFilter = filter } label: {
                    Text(filter.rawValue)
                        .font(.system(size: 11, weight: .bold))
                        .foregroundColor(selectedFilter == filter ? .white : LibraryStyle.secondary)
                        .frame(maxWidth: .infinity)
                        .frame(height: 30)
                        .background(selectedFilter == filter ? LibraryStyle.blue : LibraryStyle.thumbnail)
                        .clipShape(Capsule())
                        .frame(minHeight: 44)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityAddTraits(selectedFilter == filter ? .isSelected : [])
            }
        }
    }

    private func matchCard(_ match: LibraryMatch) -> some View {
        HStack(spacing: 12) {
            ZStack(alignment: .top) {
                RoundedRectangle(cornerRadius: 14).fill(LibraryStyle.thumbnail)
                LibraryStyle.blue.frame(height: 6).clipShape(Capsule())
                Image(systemName: "play.fill")
                    .font(.system(size: 22))
                    .foregroundColor(Color(red: 166 / 255, green: 1, blue: 0))
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .accessibilityHidden(true)
            }
            .frame(width: 110, height: 84)

            VStack(alignment: .leading, spacing: 10) {
                Text(match.title)
                    .font(.system(size: 14, weight: .bold))
                Text("\(match.competition) • \(match.replayMinutes) min")
                    .font(.system(size: 11))
                    .foregroundColor(LibraryStyle.secondary)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(11)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(LibraryStyle.card)
        .clipShape(RoundedRectangle(cornerRadius: 22))
        .contentShape(RoundedRectangle(cornerRadius: 22))
        .accessibilityHint("Opens the demo match replay")
    }

    private var bottomNavigation: some View {
        HStack(spacing: 4) {
            navigationButton("Home", destination: .home)
            Button { selectedFilter = .all; searchText = "" } label: {
                Text("Matches")
                    .font(.system(size: 11, weight: .bold))
                    .foregroundColor(.white)
                    .frame(maxWidth: .infinity, minHeight: 44)
                    .background(Color(red: 39 / 255, green: 69 / 255, blue: 119 / 255))
                    .clipShape(Capsule())
            }
            .accessibilityAddTraits(.isSelected)
            navigationButton("Saved", destination: .saved)
            navigationButton("Profile", destination: .profile)
        }
        .buttonStyle(.plain)
        .padding(5)
        .padding(.vertical, 4)
        .background(Color(red: 39 / 255, green: 48 / 255, blue: 65 / 255))
        .clipShape(RoundedRectangle(cornerRadius: 27))
        .overlay {
            RoundedRectangle(cornerRadius: 27)
                .stroke(LibraryStyle.secondary.opacity(0.45), lineWidth: 1)
        }
        .frame(maxWidth: 450)
        .padding(.horizontal, 18)
        .padding(.bottom, 8)
        .frame(maxWidth: .infinity)
        .background(LibraryStyle.background)
    }

    private func navigationButton(_ title: String, destination: LibraryDestination) -> some View {
        Button { activeDestination = destination } label: {
            Text(title)
                .font(.system(size: 11))
                .foregroundColor(LibraryStyle.secondary)
                .frame(maxWidth: .infinity, minHeight: 44)
                .contentShape(Rectangle())
        }
    }
}

private enum LibraryFilter: String, CaseIterable, Identifiable {
    case all = "All", league = "League", cup = "Cup", recent = "Recent"
    var id: String { rawValue }
}

private enum LibraryDestination: String, Identifiable {
    case home, saved, profile
    var id: String { rawValue }
}

private enum LibraryCategory {
    case league, cup
}

private struct LibraryMatch: Identifiable {
    let id: String
    let homeTeam: String
    let awayTeam: String
    let homeScore: Int
    let awayScore: Int
    let competition: String
    let category: LibraryCategory
    let date: Date
    let replayMinutes: Int

    var title: String { "\(homeTeam) \(homeScore)–\(awayScore) \(awayTeam)" }

    // Fixed sample dates (November 2026) demonstrate ordering without a backend.
    static let samples = [
        LibraryMatch(id: "city-reds", homeTeam: "City Blues", awayTeam: "Reds", homeScore: 3, awayScore: 2,
                     competition: "Championship", category: .league, date: Date(timeIntervalSince1970: 1794268800), replayMinutes: 12),
        LibraryMatch(id: "north-west", homeTeam: "North FC", awayTeam: "West", homeScore: 1, awayScore: 1,
                     competition: "Premier Cup", category: .cup, date: Date(timeIntervalSince1970: 1794441600), replayMinutes: 8),
        LibraryMatch(id: "athletic-river", homeTeam: "Athletic", awayTeam: "River", homeScore: 2, awayScore: 0,
                     competition: "League", category: .league, date: Date(timeIntervalSince1970: 1794355200), replayMinutes: 10)
    ]
}

private enum LibraryStyle {
    static let background = Color(red: 12 / 255, green: 16 / 255, blue: 32 / 255)
    static let card = Color(red: 26 / 255, green: 38 / 255, blue: 61 / 255)
    static let thumbnail = Color(red: 30 / 255, green: 48 / 255, blue: 76 / 255)
    static let blue = Color(red: 40 / 255, green: 120 / 255, blue: 240 / 255)
    static let primary = Color(red: 240 / 255, green: 243 / 255, blue: 251 / 255)
    static let secondary = Color(red: 166 / 255, green: 185 / 255, blue: 209 / 255)
}

#Preview {
    MatchLibraryView()
}
