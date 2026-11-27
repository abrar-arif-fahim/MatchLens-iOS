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
    static let accentText = Color(uiColor: UIColor { traits in
        traits.userInterfaceStyle == .dark ? UIColor(red: 166 / 255, green: 1, blue: 0, alpha: 1)
            : UIColor(red: 0.23, green: 0.36, blue: 0.03, alpha: 1)
    })
}
struct DataNotice: View {
    let title: String
    let message: String
    var retry: (() -> Void)? = nil
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title).font(.headline).accessibilityAddTraits(.isHeader)
            Text(message).font(.subheadline).foregroundStyle(MatchLensStyle.secondary)
            if let retry {
                Button("Retry", action: retry)
                    .buttonStyle(.bordered).controlSize(.large)
                    .accessibilityLabel("Retry: \(title)")
            }
        }
        .fixedSize(horizontal: false, vertical: true)
        .padding(20).frame(maxWidth: .infinity, alignment: .leading)
        .background(MatchLensStyle.card).clipShape(RoundedRectangle(cornerRadius: 20))
    }
}

/// An initial-load placeholder. Existing content stays visible during refreshes.
struct LoadingCard: View {
    let title: String
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            ProgressView(title).font(.subheadline)
            VStack(alignment: .leading, spacing: 8) {
                Capsule().frame(maxWidth: 180).frame(height: 12)
                Capsule().frame(maxWidth: 110).frame(height: 8)
            }
            .foregroundStyle(MatchLensStyle.secondary.opacity(0.18))
            .accessibilityHidden(true)
        }
        .padding(20).frame(maxWidth: .infinity, alignment: .leading)
        .background(MatchLensStyle.card).clipShape(RoundedRectangle(cornerRadius: 20))
    }
}

struct ArtworkPlaceholder: View {
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    let symbol: String
    var width: CGFloat = 64
    var height: CGFloat = 56

    var body: some View {
        Image(systemName: symbol)
            .font(.title2)
            .foregroundStyle(MatchLensStyle.accentText)
            .frame(width: dynamicTypeSize.isAccessibilitySize ? min(width, 48) : width,
                   height: dynamicTypeSize.isAccessibilitySize ? min(height, 48) : height)
            .background(MatchLensStyle.blue.opacity(0.12))
            .clipShape(RoundedRectangle(cornerRadius: 14))
            .accessibilityHidden(true)
    }
}

struct AdaptiveActionRow<Content: View>: View {
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @ViewBuilder var content: () -> Content

    var body: some View {
        let layout = dynamicTypeSize.isAccessibilitySize
            ? AnyLayout(VStackLayout(alignment: .leading, spacing: 8))
            : AnyLayout(HStackLayout(alignment: .center, spacing: 8))
        layout { content() }
    }
}
struct MatchCardRow: View {
    let card: MatchCard
    var body: some View {
        HStack(spacing: 12) {
            ArtworkPlaceholder(symbol: "sportscourt.fill", width: 100, height: 80)
            VStack(alignment: .leading, spacing: 8) {
                Text(card.title).font(.subheadline.bold())
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
    private var showsFeedback: Bool {
        app.savedActionID == kind.savedDocumentID(id, watchlist: false)
            || (kind == .match && app.savedActionID == kind.savedDocumentID(id, watchlist: true))
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            AdaptiveActionRow {
                SavedToggle(kind: kind, id: id, watchlist: false)
                if kind == .match {
                    SavedToggle(kind: kind, id: id, watchlist: true)
                }
            }
            .buttonStyle(.bordered).controlSize(.large).tint(MatchLensStyle.blue).disabled(app.saving)
            if showsFeedback {
                if app.saving { ProgressView("Updating saved item…") }
                if let error = app.mutationMessage { Text(error).font(.caption).foregroundStyle(.red) }
                if let success = app.mutationSuccess { Text(success).font(.caption).foregroundStyle(.green) }
            }
        }
    }
}

private struct SavedToggle: View {
    @EnvironmentObject private var app: AppStore
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    let kind: SavedKind
    let id: String
    let watchlist: Bool
    @State private var error: String?
    private var saved: Bool? { app.savedStatus(kind, id: id, watchlist: watchlist) }

    var body: some View {
        Group {
            if let saved {
                Button {
                    Task { await app.setSaved(kind, id: id, saved: !saved, watchlist: watchlist) }
                } label: {
                    Label(watchlist ? (saved ? "Remove from watchlist" : "Add to watchlist")
                                    : (saved ? "Remove favorite" : "Save favorite"),
                          systemImage: watchlist ? (saved ? "bookmark.fill" : "bookmark")
                                                : (saved ? "star.fill" : "star"))
                        .foregroundStyle(saved ? MatchLensStyle.accentText : MatchLensStyle.primary)
                        .animation(reduceMotion ? nil : .easeInOut(duration: 0.18), value: saved)
                }
                .accessibilityAddTraits(saved ? .isSelected : [])
            } else if let error {
                VStack(alignment: .leading) {
                    Text(error).font(.caption).foregroundStyle(.red)
                    Button(watchlist ? "Retry watchlist status" : "Retry favorite status") {
                        Task { await loadStatus() }
                    }
                }
            } else {
                ProgressView(watchlist ? "Checking watchlist…" : "Checking favorite…")
            }
        }
        .task(id: id) { await loadStatus() }
    }

    private func loadStatus() async {
        error = nil
        do { try await app.loadSavedStatus(kind, id: id, watchlist: watchlist) }
        catch { if !Task.isCancelled { self.error = FirebaseSetup.safeMessage(error) } }
    }
}
