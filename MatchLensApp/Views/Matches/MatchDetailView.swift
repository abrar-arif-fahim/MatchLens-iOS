import SwiftUI

struct MatchDetailView: View {
    @EnvironmentObject private var app: AppStore
    let matchID: String
    @State private var detail: MatchDetail?
    @State private var error: String?
    @State private var loading = false
    var body: some View {
        ZStack {
            MatchLensStyle.background.ignoresSafeArea()
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    if loading { ProgressView("Loading match details…") }
                    if let error { DataNotice(title: "Match data unavailable", message: error); Button("Retry") { Task { await load() } } }
                    if let detail {
                        let card = detail.card
                        if card.match.isDemo { DataNotice(title: "FICTIONAL DEMONSTRATION", message: "This is not a real match result.") }
                        Text(card.title).font(.title.bold())
                        Text(card.match.finalScore.text).font(.system(size: 36, weight: .bold)).monospacedDigit()
                        Text(card.match.status.capitalized + " • " + card.competition.name + " • " + card.match.season)
                            .foregroundStyle(MatchLensStyle.secondary)
                        Text(ClientPresentation.utc(card.match.kickoff))
                        if let finish = card.match.finishType {
                            DataNotice(title: ["regularTime": "Regular-time result", "extraTime": "After extra time", "penalties": "Penalty shootout"][finish] ?? "Finished",
                                message: "Regular time: \(card.match.regularTime.text)\nExtra-time period: \(card.match.extraTime.text)\nShootout: \(card.match.penalties.text)")
                        }
                        HStack {
                            NavigationLink(card.home.name) { TeamProfileView(teamID: card.home.id) }
                            NavigationLink(card.away.name) { TeamProfileView(teamID: card.away.id) }
                        }
                        SaveControls(kind: .match, id: card.id)
                        NavigationLink("Match analysis and events") { MatchAnalysisView(detail: detail) }
                            .buttonStyle(.borderedProminent)
                        Text("Highlights").font(.title2.bold())
                        if detail.highlights.isEmpty { DataNotice(title: "No highlights published", message: "No authorized playback is available.") }
                        ForEach(detail.highlights) { highlight in
                            NavigationLink { MatchReplayView(detail: detail, highlight: highlight) } label: {
                                DataNotice(title: highlight.title, message: "Event timeline metadata • Video unavailable")
                            }.buttonStyle(.plain)
                            SaveControls(kind: .highlight, id: highlight.id)
                        }
                        HStack {
                            if detail.eventsCursor != nil { Button("Load more events") { Task { await load(mode: .events) } } }
                            if detail.highlightsCursor != nil { Button("More highlight metadata") { Task { await load(mode: .highlights) } } }
                        }.disabled(loading)
                        Text("Source: \(card.match.source)\nStatistics and lineups have not been collected.")
                            .font(.caption).foregroundStyle(MatchLensStyle.secondary)
                    }
                }.padding(22).frame(maxWidth: 480).frame(maxWidth: .infinity)
            }.refreshable { await load() }
        }
        .foregroundStyle(MatchLensStyle.primary).navigationTitle("Match details").navigationBarTitleDisplayMode(.inline)
        .toolbar(.visible, for: .navigationBar).task(id: matchID) { await load() }
    }
    private enum LoadMode { case initial, events, highlights }
    private func load(mode: LoadMode = .initial) async {
        guard !loading, let repo = app.repository else { return }
        let key = app.sessionKey, old = detail
        loading = true; error = nil
        defer { if app.isCurrent(key) { loading = false } }
        do {
            let page = try await repo.detail(matchID, eventCursor: mode == .events ? old?.eventsCursor : nil,
                                             highlightCursor: mode == .highlights ? old?.highlightsCursor : nil)
            guard app.isCurrent(key), !Task.isCancelled else { return }
            if mode == .initial || old == nil { detail = page }
            else if let old {
                let events = old.events.filter { row in !page.events.contains { $0.id == row.id } } + page.events
                let highlights = old.highlights.filter { row in !page.highlights.contains { $0.id == row.id } } + page.highlights
                detail = MatchDetail(card: page.card, events: events.sorted {
                    ($0.minute ?? Int.max, $0.addedTime ?? 0, $0.id) < ($1.minute ?? Int.max, $1.addedTime ?? 0, $1.id)
                }, highlights: highlights, players: old.players.merging(page.players) { _, new in new },
                    eventsCursor: mode == .highlights ? old.eventsCursor : page.eventsCursor,
                    highlightsCursor: mode == .events ? old.highlightsCursor : page.highlightsCursor)
            }
        } catch { if app.isCurrent(key) { self.error = FirebaseSetup.safeMessage(error) } }
    }
}
