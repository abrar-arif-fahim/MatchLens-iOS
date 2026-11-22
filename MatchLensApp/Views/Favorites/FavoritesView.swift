import SwiftUI

struct FavoritesView: View {
    @EnvironmentObject private var app: AppStore
    @State private var isWatchlist = false
    private var items: [SavedItem] { isWatchlist ? app.watchlist : app.favorites }
    private var listError: String? { isWatchlist ? app.watchlistError : app.favoritesError }
    private var listLoading: Bool { isWatchlist ? app.watchlistLoading : app.favoritesLoading }
    var body: some View {
        NavigationStack {
            ZStack {
                MatchLensStyle.background.ignoresSafeArea()
                ScrollView {
                    VStack(alignment: .leading, spacing: 18) {
                        Text("Saved Moments").font(.system(size: 28, weight: .bold))
                        Text("Your private collection").font(.caption).foregroundStyle(MatchLensStyle.secondary)
                        Picker("Saved list", selection: $isWatchlist) {
                            Text("Favorites").tag(false); Text("Watchlist").tag(true)
                        }.pickerStyle(.segmented)
                        if listLoading { ProgressView("Loading your saved items…") }
                        if let error = listError {
                            DataNotice(title: "Saved items unavailable", message: error)
                            Button("Retry") { Task { await app.loadSaved(watchlist: isWatchlist, reset: true) } }
                        }
                        if items.isEmpty && !listLoading && listError == nil {
                            DataNotice(title: "Nothing saved yet", message: isWatchlist ? "Add matches to your watchlist from match details." : "Save players, teams, matches or highlight metadata from their details.")
                        }
                        ForEach(items) { item in
                            HStack {
                                if item.available {
                                    NavigationLink { SavedDestination(item: item) } label: { savedCard(item) }.buttonStyle(.plain)
                                } else { savedCard(item) }
                                Menu {
                                    Button("Remove", role: .destructive) {
                                        Task { await app.setSaved(item.record.kind, id: item.record.targetId, saved: false, watchlist: item.record.watchlist) }
                                    }
                                } label: { Image(systemName: "ellipsis.circle").frame(width: 44, height: 44) }
                                .disabled(app.saving)
                            }
                        }
                        if (isWatchlist ? app.watchlistCursor : app.favoritesCursor) != nil {
                            Button("Load more saved items") { Task { await app.loadSaved(watchlist: isWatchlist, more: true) } }
                                .disabled(listLoading)
                        }
                        if app.saving { ProgressView("Updating…") }
                        if let error = app.mutationMessage { Text(error).font(.caption).foregroundStyle(.red) }
                        if let success = app.mutationSuccess { Text(success).font(.caption).foregroundStyle(.green) }
                        DataNotice(title: "Saved highlight metadata", message: "A saved highlight does not grant playback permission. No video is currently available.")
                    }
                    .foregroundStyle(MatchLensStyle.primary).padding(22).frame(maxWidth: 480).frame(maxWidth: .infinity)
                }
                .refreshable { await app.loadSaved(watchlist: isWatchlist, reset: true) }
            }
            .toolbar(.hidden, for: .navigationBar)
        }
        .tint(MatchLensStyle.blue)
        .task(id: isWatchlist) { await app.loadSaved(watchlist: isWatchlist) }
    }
    private func savedCard(_ item: SavedItem) -> some View {
        HStack(spacing: 12) {
            Image(systemName: "star.fill").font(.title2).foregroundStyle(MatchLensStyle.lime)
                .frame(width: 90, height: 84).background(MatchLensStyle.blue.opacity(0.15))
                .clipShape(RoundedRectangle(cornerRadius: 14))
            VStack(alignment: .leading, spacing: 10) {
                Text(item.title).font(.system(size: 14, weight: .bold))
                Text(item.record.kind.rawValue.capitalized + " • " + item.subtitle)
                    .font(.caption).foregroundStyle(MatchLensStyle.secondary)
            }.frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(10).background(MatchLensStyle.card).clipShape(RoundedRectangle(cornerRadius: 22))
        .contentShape(RoundedRectangle(cornerRadius: 22))
    }
}
private struct SavedDestination: View {
    let item: SavedItem
    var body: some View {
        switch item.record.kind {
        case .player: PlayerProfileView(playerID: item.record.targetId)
        case .team: TeamProfileView(teamID: item.record.targetId)
        case .match: MatchDetailView(matchID: item.record.targetId)
        case .highlight:
            if let id = item.matchId { MatchDetailView(matchID: id) }
            else { DataNotice(title: "Unavailable", message: "The parent match needs review.") }
        }
    }
}
#Preview { FavoritesView().environmentObject(AppStore()) }
