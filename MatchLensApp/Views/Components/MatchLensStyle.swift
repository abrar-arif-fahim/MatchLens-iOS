import SwiftUI
import UIKit

enum MatchLensStyle {
    static let background = Color(uiColor: UIColor { traits in
        traits.userInterfaceStyle == .dark ? UIColor(red: 12 / 255, green: 16 / 255, blue: 32 / 255, alpha: 1)
            : UIColor(red: 0.95, green: 0.96, blue: 0.98, alpha: 1)
    })
    static let card = Color(uiColor: UIColor { traits in
        traits.userInterfaceStyle == .dark ? UIColor(red: 26 / 255, green: 38 / 255, blue: 61 / 255, alpha: 1) : .white
    })
    static let primary = Color.primary
    static let blue = Color(red: 41 / 255, green: 119 / 255, blue: 250 / 255)
    static let secondary = Color(uiColor: UIColor { traits in
        traits.userInterfaceStyle == .dark ? UIColor(red: 166 / 255, green: 185 / 255, blue: 209 / 255, alpha: 1) : .darkGray
    })
    static let lime = Color(red: 166 / 255, green: 1, blue: 0)
}
struct DataNotice: View {
    let title: String
    let message: String
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title).font(.headline)
            Text(message).font(.subheadline).foregroundStyle(MatchLensStyle.secondary)
        }
        .padding(20).frame(maxWidth: .infinity, alignment: .leading)
        .background(MatchLensStyle.card).clipShape(RoundedRectangle(cornerRadius: 20))
    }
}
struct MatchCardRow: View {
    let card: MatchCard
    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: "sportscourt.fill")
                .font(.title).foregroundStyle(MatchLensStyle.lime)
                .frame(width: 100, height: 80).background(MatchLensStyle.card.opacity(0.7))
                .clipShape(RoundedRectangle(cornerRadius: 14))
            VStack(alignment: .leading, spacing: 8) {
                Text(card.title).font(.system(size: 14, weight: .bold))
                Text(card.match.finalScore.text + " • " + card.match.status.capitalized)
                    .font(.caption).foregroundStyle(MatchLensStyle.secondary)
                Text(card.competition.name).font(.caption).foregroundStyle(MatchLensStyle.secondary)
                if card.match.isDemo { Text("DEMO — fictional match").font(.caption).foregroundStyle(.orange) }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(11).background(MatchLensStyle.card).clipShape(RoundedRectangle(cornerRadius: 22))
        .foregroundStyle(MatchLensStyle.primary).contentShape(RoundedRectangle(cornerRadius: 22))
    }
}
struct SaveControls: View {
    @EnvironmentObject private var app: AppStore
    let kind: SavedKind, id: String
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Button("Save favorite") { Task { await app.setSaved(kind, id: id, saved: true) } }
                if kind == .match {
                    Button("Add to watchlist") { Task { await app.setSaved(.match, id: id, saved: true, watchlist: true) } }
                }
            }
            .buttonStyle(.bordered).tint(MatchLensStyle.blue).disabled(app.saving)
            if app.saving { ProgressView("Saving…") }
            if let error = app.mutationMessage { Text(error).font(.caption).foregroundStyle(.red) }
            if let success = app.mutationSuccess { Text(success).font(.caption).foregroundStyle(.green) }
        }
    }
}
