import SwiftUI

struct MatchLibraryView: View {
    @EnvironmentObject private var app: AppStore
    @State private var searchText = ""
    @State private var selectedFilter: LibraryFilter = .all
    private var filtered: [MatchCard] {
        let needle = ClientPresentation.normalized(searchText)
        return app.matches.filter { card in
            let text = ClientPresentation.normalized(card.title + " " + card.competition.name)
            return (needle.isEmpty || text.contains(needle)) &&
                (selectedFilter == .all || selectedFilter == .recent ||
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
                        Text("Match Library").font(.system(size: 28, weight: .bold))
                        Text("Browse published football matches").font(.caption).foregroundStyle(MatchLensStyle.secondary)
                        HStack {
                            Image(systemName: "magnifyingglass")
                            TextField("Search loaded teams or matches", text: $searchText)
                                .textInputAutocapitalization(.never).autocorrectionDisabled()
                        }.padding(16).background(MatchLensStyle.card).clipShape(RoundedRectangle(cornerRadius: 17))
                        HStack {
                            ForEach(LibraryFilter.allCases) { filter in
                                Button { selectedFilter = filter } label: {
                                    Text(filter.rawValue).font(.system(size: 11, weight: .bold))
                                        .frame(maxWidth: .infinity, minHeight: 44)
                                        .background(selectedFilter == filter ? MatchLensStyle.blue : MatchLensStyle.card)
                                        .clipShape(Capsule())
                                }.buttonStyle(.plain)
                            }
                        }
                        NavigationLink("Search players and teams") { CatalogView() }
                        if app.matchesLoading { ProgressView("Loading…").tint(.white) }
                        if let error = app.matchesError {
                            DataNotice(title: "Could not load matches", message: error)
                            Button("Retry") { Task { await app.loadMatches(reset: true) } }
                        } else if filtered.isEmpty && !app.matchesLoading {
                            DataNotice(title: "No matches found", message: app.matchesCursor == nil ? "No matching published data is available." : "No match in the loaded pages. Load more to continue searching.")
                        }
                        ForEach(filtered) { card in
                            NavigationLink { MatchDetailView(matchID: card.id) } label: { MatchCardRow(card: card) }.buttonStyle(.plain)
                        }
                        if app.matchesCursor != nil {
                            Button("Load more matches") { Task { await app.loadMatches(more: true) } }.disabled(app.matchesLoading)
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
