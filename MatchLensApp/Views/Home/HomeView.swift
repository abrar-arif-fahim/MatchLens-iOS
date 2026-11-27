import SwiftUI

struct HomeView: View {
    @EnvironmentObject private var app: AppStore
    var body: some View {
        NavigationStack {
            ZStack {
                MatchLensStyle.background.ignoresSafeArea()
                ScrollView {
                    VStack(alignment: .leading, spacing: 20) {
                        VStack(alignment: .leading, spacing: 6) {
                            Text("FOOTBALL / DISCOVER").font(.system(size: 12)).foregroundStyle(MatchLensStyle.secondary)
                            Text("MatchLens").font(.largeTitle.bold()).accessibilityAddTraits(.isHeader)
                            Text("Every moment matters.").font(.system(size: 15)).foregroundStyle(MatchLensStyle.secondary)
                        }
                        if app.matches.isEmpty && app.matchesError == nil && (app.matchesLoading || !app.loadedMatches) {
                            LoadingCard(title: "Loading matches…")
                        }
                        if let error = app.matchesError {
                            DataNotice(title: app.matches.isEmpty ? "Matches unavailable" : "Couldn’t update matches", message: error) {
                                Task { await app.loadMatches(reset: true) }
                            }
                        }
                        if let first = app.matches.first {
                            featuredMatch(first)
                        } else if app.loadedMatches && !app.matchesLoading && app.matchesError == nil {
                            DataNotice(title: "No matches available", message: app.matchesCursor == nil
                                ? "No approved matches are available to display. You can explore players and teams."
                                : "No matches could be displayed from the loaded page. Load more to check the next page.")
                        }
                        AdaptiveActionRow {
                            NavigationLink { CatalogView() } label: { Label("Players & teams", systemImage: "magnifyingglass") }
                                .buttonStyle(.borderedProminent)
                            Button("Match library") { app.tab = .matches }.buttonStyle(.bordered)
                        }
                        Text("Latest matches").font(.title3.bold()).accessibilityAddTraits(.isHeader)
                        ForEach(app.matches) { card in
                            NavigationLink { MatchDetailView(matchID: card.id) } label: { MatchCardRow(card: card) }.buttonStyle(.plain)
                        }
                        if app.matchesCursor != nil {
                            Button(app.matchesLoading ? "Loading matches…" : "Load more matches") {
                                Task { await app.loadMatches(more: true) }
                            }.disabled(app.matchesLoading)
                        }
                        if app.reviewCount > 0 { Text("\(app.reviewCount) fetched match records require a data review.").font(.caption).foregroundStyle(.orange) }
                        DataNotice(title: "Highlight videos", message: "No authorized video is available. Match details can show event metadata when provided.")
                    }
                    .foregroundStyle(MatchLensStyle.primary).frame(maxWidth: 440, alignment: .leading)
                    .padding(.horizontal, 22).padding(.top, 18).padding(.bottom, 30).frame(maxWidth: .infinity)
                }
                .refreshable { await app.loadMatches(reset: true) }
            }
            .toolbar(.hidden, for: .navigationBar)
        }
        .tint(MatchLensStyle.blue)
        .task { await app.loadMatches() }
    }
    private func featuredMatch(_ card: MatchCard) -> some View {
        VStack(alignment: .leading, spacing: 16) {
            MatchLensStyle.blue.frame(height: 8).clipShape(Capsule())
            VStack(alignment: .leading, spacing: 16) {
                Text("FEATURED MATCH").font(.system(size: 11, weight: .bold)).foregroundStyle(MatchLensStyle.lime)
                Text(card.title).font(.title.bold()).foregroundStyle(.white)
                Text(card.match.finalScore.text + " • " + card.match.status.capitalized).foregroundStyle(.white.opacity(0.8))
                Text(ClientPresentation.utc(card.match.kickoff)).font(.caption).foregroundStyle(.white.opacity(0.8))
                NavigationLink("MATCH DETAILS") { MatchDetailView(matchID: card.id) }
                    .font(.system(size: 11, weight: .bold)).buttonStyle(.borderedProminent)
            }.padding(18)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(red: 30 / 255, green: 48 / 255, blue: 76 / 255))
        .clipShape(RoundedRectangle(cornerRadius: 24))
    }
}
#Preview { HomeView().environmentObject(AppStore()) }
