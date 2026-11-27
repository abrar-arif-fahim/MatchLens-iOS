import SwiftUI

struct MatchLibraryView: View {
    @EnvironmentObject private var app: AppStore
    @State private var searchText = ""
    @State private var selectedFilter: LibraryFilter = .all
    private var filtered: [MatchCard] {
        let needle = ClientPresentation.normalized(searchText)
        let now = Date()
        let recentStart = now.addingTimeInterval(-30 * 24 * 60 * 60)
        return app.matches.filter { card in
            let text = ClientPresentation.normalized(card.title + " " + card.competition.name)
            let isRecent = card.match.kickoff.map { (recentStart...now).contains($0) } ?? false
            return (needle.isEmpty || text.contains(needle)) &&
                (selectedFilter == .all || (selectedFilter == .recent && isRecent) ||
                 (selectedFilter == .league && card.competition.kind == "domesticLeague") ||
                 (selectedFilter == .cup && card.competition.kind == "nationalCup"))
        }
    }
    var body: some View {
        NavigationStack {
            ZStack {
                MatchLensStyle.background.ignoresSafeArea()
                ScrollView {
                    VStack(alignment: .leading, spacing: 18) {
                        Text("Match Library").font(.title.bold()).accessibilityAddTraits(.isHeader)
                        Text("Browse published football matches").font(.caption).foregroundStyle(MatchLensStyle.secondary)
                        HStack {
                            Image(systemName: "magnifyingglass").accessibilityHidden(true)
                            TextField("Search loaded teams or matches", text: $searchText)
                                .textInputAutocapitalization(.never).autocorrectionDisabled()
                            if !searchText.isEmpty {
                                Button { searchText = "" } label: {
                                    Image(systemName: "xmark.circle.fill").frame(width: 44, height: 44)
                                        .contentShape(Rectangle())
                                }.buttonStyle(.plain).accessibilityLabel("Clear match search")
                            }
                        }.padding(16).background(MatchLensStyle.card).clipShape(RoundedRectangle(cornerRadius: 17))
                        AdaptiveActionRow {
                            ForEach(LibraryFilter.allCases) { filter in
                                Button { selectedFilter = filter } label: {
                                    Text(filter.rawValue).font(.caption.bold())
                                        .frame(maxWidth: .infinity, minHeight: 44)
                                        .background(selectedFilter == filter ? MatchLensStyle.blue : MatchLensStyle.card)
                                        .clipShape(Capsule())
                                }.buttonStyle(.plain).accessibilityAddTraits(selectedFilter == filter ? .isSelected : [])
                            }
                        }
                        NavigationLink("Search players and teams") { CatalogView() }
                        if selectedFilter == .recent {
                            Text("Recent covers the past 30 days.").font(.caption).foregroundStyle(MatchLensStyle.secondary)
                        }
                        if app.matches.isEmpty && app.matchesError == nil && (app.matchesLoading || !app.loadedMatches) {
                            LoadingCard(title: "Loading matches…")
                        }
                        if let error = app.matchesError {
                            DataNotice(title: app.matches.isEmpty ? "Couldn’t load matches" : "Couldn’t update matches", message: error) {
                                Task { await app.loadMatches(reset: true) }
                            }
                        } else if filtered.isEmpty && app.loadedMatches && !app.matchesLoading {
                            DataNotice(title: "No matches found", message: app.matchesCursor == nil ? "No matching published data is available." : "No match in the loaded pages. Load more to continue searching.")
                        }
                        ForEach(filtered) { card in
                            NavigationLink { MatchDetailView(matchID: card.id) } label: { MatchCardRow(card: card) }.buttonStyle(.plain)
                        }
                        if app.matchesCursor != nil {
                            Button(app.matchesLoading ? "Loading matches…" : "Load more matches") {
                                Task { await app.loadMatches(more: true) }
                            }.disabled(app.matchesLoading)
                        }
                        Text("Results cover loaded pages. Match times are shown in UTC.").font(.caption).foregroundStyle(MatchLensStyle.secondary)
                    }
                    .foregroundStyle(MatchLensStyle.primary).frame(maxWidth: 440, alignment: .leading).padding(22).frame(maxWidth: .infinity)
                }
                .refreshable { await app.loadMatches(reset: true) }
                .scrollDismissesKeyboard(.interactively)
            }
            .toolbar(.hidden, for: .navigationBar)
        }
        .tint(MatchLensStyle.blue)
        .task { await app.loadMatches() }
    }
}
private enum LibraryFilter: String, CaseIterable, Identifiable {
    case all = "All", league = "League", cup = "Cup", recent = "Recent"
    var id: String { rawValue }
}
#Preview { MatchLibraryView().environmentObject(AppStore()) }
