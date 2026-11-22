import SwiftUI

struct MatchAnalysisView: View {
    @Environment(\.dismiss) private var dismiss
    let detail: MatchDetail
    var body: some View {
        ZStack {
            MatchLensStyle.background.ignoresSafeArea()
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    HStack {
                        Button { dismiss() } label: { Image(systemName: "chevron.left").frame(width: 32, height: 44) }
                            .accessibilityLabel("Back")
                        Text("Match Analysis").font(.system(size: 22, weight: .bold))
                    }.buttonStyle(.plain)
                    if detail.card.match.isDemo {
                        DataNotice(title: "FICTIONAL DEMONSTRATION", message: "These scores and events are not a real football result.")
                    }
                    VStack(spacing: 16) {
                        HStack {
                            Text(detail.card.home.name).frame(maxWidth: .infinity, alignment: .leading)
                            Text(detail.card.away.name).frame(maxWidth: .infinity, alignment: .trailing)
                        }.font(.system(size: 13, weight: .bold)).foregroundStyle(MatchLensStyle.secondary)
                        Text(detail.card.match.finalScore.text).font(.system(size: 32, weight: .bold)).monospacedDigit()
                        Text(detail.card.match.status.capitalized).foregroundStyle(MatchLensStyle.secondary)
                    }
                    .padding(20).frame(maxWidth: .infinity).background(MatchLensStyle.card)
                    .clipShape(RoundedRectangle(cornerRadius: 23))
                    Text("Match Statistics").font(.title2.bold())
                    DataNotice(title: "Statistics unavailable", message: "Verified statistics and lineups have not been collected.")
                    Text("Key Events").font(.title2.bold())
                    if detail.events.isEmpty { Text("No event metadata is available.").foregroundStyle(MatchLensStyle.secondary) }
                    ForEach(detail.events) { event in
                        VStack(alignment: .leading, spacing: 8) {
                            Text(event.clock + " • " + (["goal": "Goal", "yellowCard": "Yellow card", "redCard": "Red card",
                                "save": "Save", "substitution": "Substitution", "other": "Event"][event.kind] ?? "Event"))
                                .font(.caption).foregroundStyle(MatchLensStyle.secondary)
                            Text(event.label).font(.headline)
                            if let playerID = event.playerId, let player = detail.players[playerID] {
                                NavigationLink(player.name) { PlayerProfileView(playerID: player.id) }
                            }
                        }.padding(16).frame(maxWidth: .infinity, alignment: .leading)
                            .background(MatchLensStyle.card).clipShape(RoundedRectangle(cornerRadius: 18))
                    }
                    if detail.eventsCursor != nil {
                        Text("More events are available. Return to match details to load the next page.")
                            .font(.caption).foregroundStyle(MatchLensStyle.secondary)
                    }
                    Text("Event lists can be incomplete and never recalculate the match score.")
                        .font(.caption).foregroundStyle(MatchLensStyle.secondary)
                }
                .foregroundStyle(MatchLensStyle.primary).frame(maxWidth: 440, alignment: .leading)
                .padding(22).frame(maxWidth: .infinity)
            }
        }
        .navigationBarBackButtonHidden(true).toolbar(.hidden, for: .navigationBar)
    }
}
#Preview { DataNotice(title: "Match analysis", message: "Open an actual match record to inspect its analysis.") }
