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
                            Text("MatchLens").font(.system(size: 32, weight: .bold)).accessibilityAddTraits(.isHeader)
                            Text("Every moment matters.").font(.system(size: 15)).foregroundStyle(MatchLensStyle.secondary)
                        }
                        if app.matchesLoading { ProgressView("Loading matches…").tint(.white) }
                        if let error = app.matchesError {
                            DataNotice(title: "Matches unavailable", message: error)
                            Button("Retry") { Task { await app.loadMatches(reset: true) } }
                        } else if let first = app.matches.first {
                            featuredMatch(first)
                        } else if !app.matchesLoading {
                            DataNotice(title: "No matches available", message: "Approved match data has not been published yet. You can explore players and teams.")
                        }
                        HStack {
                            NavigationLink { CatalogView() } label: { Label("Players & teams", systemImage: "magnifyingglass") }
                                .buttonStyle(.borderedProminent)
                            Button("Match library") { app.tab = .matches }.buttonStyle(.bordered)
                        }
                        Text("Latest matches").font(.system(size: 20, weight: .bold))
                        ForEach(app.matches) { card in
                            NavigationLink { MatchDetailView(matchID: card.id) } label: { MatchCardRow(card: card) }.buttonStyle(.plain)
                        }
                        if app.matchesCursor != nil {
                            Button("Load more matches") { Task { await app.loadMatches(more: true) } }.disabled(app.matchesLoading)
                        }
                        if app.reviewCount > 0 { Text("\(app.reviewCount) fetched records require a data review.").font(.caption).foregroundStyle(.orange) }
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
                Text(card.title).font(.system(size: 26, weight: .bold)).foregroundStyle(.white)
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
