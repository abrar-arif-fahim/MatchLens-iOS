import SwiftUI

struct MatchReplayView: View {
    @Environment(\.dismiss) private var dismiss
    let detail: MatchDetail
    let highlight: HighlightRecord
    @State private var selectedFilter: ReplayFilter = .all
    @State private var selectedSeconds: Double?
    @State private var showVideoUnavailable = false

    private var rows: [VideoMarker] {
        highlight.markers.filter { marker in
            guard let event = detail.events.first(where: { $0.id == marker.eventId }) else { return false }
            switch selectedFilter {
            case .all: return true
            case .goals: return event.kind == "goal"
            case .saves: return event.kind == "save"
            case .cards: return event.kind == "yellowCard" || event.kind == "redCard"
            }
        }
    }
    var body: some View {
        ZStack {
            MatchLensStyle.background.ignoresSafeArea()
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    HStack {
                        Button { dismiss() } label: { Image(systemName: "chevron.left").frame(width: 32, height: 44) }
                            .accessibilityLabel("Back")
                        Text("Match Replay").font(.system(size: 22, weight: .bold))
                    }.buttonStyle(.plain)
                    ZStack(alignment: .bottomLeading) {
                        Color(red: 23 / 255, green: 45 / 255, blue: 75 / 255)
                        Button { showVideoUnavailable = true } label: {
                            Image(systemName: "video.slash.fill").font(.system(size: 42)).foregroundStyle(.white)
                                .frame(maxWidth: .infinity, maxHeight: .infinity).contentShape(Rectangle())
                        }.buttonStyle(.plain).accessibilityLabel("Video unavailable")
                        Text(detail.card.title).font(.headline).foregroundStyle(.white).padding(24).allowsHitTesting(false)
                    }
                    .frame(height: 194).clipShape(RoundedRectangle(cornerRadius: 21))
                    .overlay(alignment: .top) { MatchLensStyle.blue.frame(height: 7).clipShape(Capsule()) }
                    if detail.card.match.isDemo { Text("DEMO — fictional match and marker positions").foregroundStyle(.orange) }
                    Text(highlight.title).font(.title3.bold())
                    Text("Metadata only • No authorized video is available").font(.caption).foregroundStyle(MatchLensStyle.secondary)
                    metadataTimeline
                    Text("Select a moment").font(.title2.bold())
                    HStack {
                        ForEach(ReplayFilter.allCases) { filter in
                            Button { selectedFilter = filter } label: {
                                Text(filter.rawValue).font(.system(size: 11, weight: .bold))
                                    .frame(maxWidth: .infinity, minHeight: 44)
                                    .background(selectedFilter == filter ? MatchLensStyle.blue : MatchLensStyle.card)
                                    .clipShape(Capsule())
                            }.buttonStyle(.plain)
                        }
                    }
                    if rows.isEmpty { Text("No markers match this filter.").foregroundStyle(MatchLensStyle.secondary) }
                    ForEach(rows, id: \.eventId) { marker in
                        if let event = detail.events.first(where: { $0.id == marker.eventId }) {
                            Button { selectedSeconds = marker.seconds } label: {
                                VStack(alignment: .leading, spacing: 6) {
                                    Text(ReplayTimeline.label(marker.seconds) + " • " + event.label).font(.headline)
                                    Text("Football clock: " + event.clock).font(.caption).foregroundStyle(MatchLensStyle.secondary)
                                }.padding(14).frame(maxWidth: .infinity, alignment: .leading)
                                    .background(MatchLensStyle.card).clipShape(RoundedRectangle(cornerRadius: 16))
                            }.buttonStyle(.plain).accessibilityHint("Selects timeline metadata; no video is played.")
                        }
                    }
                    SaveControls(kind: .highlight, id: highlight.id)
                }
                .foregroundStyle(MatchLensStyle.primary).frame(maxWidth: 440, alignment: .leading)
                .padding(22).frame(maxWidth: .infinity)
            }
        }
        .navigationBarBackButtonHidden(true).toolbar(.hidden, for: .navigationBar)
        .alert("Video unavailable", isPresented: $showVideoUnavailable) {
            Button("OK", role: .cancel) {}
        } message: { Text("Only event metadata is published. No media is downloaded or played.") }
    }
    @ViewBuilder private var metadataTimeline: some View {
        if let duration = highlight.duration {
            VStack(spacing: 8) {
                HStack {
                    Text(selectedSeconds.map(ReplayTimeline.label) ?? "Select a marker")
                    Spacer()
                    Text(ReplayTimeline.label(duration))
                }.font(.caption).monospacedDigit()
                GeometryReader { geometry in
                    ZStack(alignment: .leading) {
                        Capsule().fill(MatchLensStyle.card).frame(height: 7)
                        Capsule().fill(MatchLensStyle.blue)
                            .frame(width: geometry.size.width * CGFloat((selectedSeconds ?? 0) / duration), height: 7)
                        ForEach(highlight.markers, id: \.eventId) { marker in
                            RoundedRectangle(cornerRadius: 1.5).fill(MatchLensStyle.lime).frame(width: 4, height: 16)
                                .offset(x: max(0, geometry.size.width - 4) * CGFloat(marker.seconds / duration))
                        }
                    }.frame(height: 32)
                }.frame(height: 32).accessibilityHidden(true)
                Text("Clip seconds and football minutes are separate coordinates.")
                    .font(.caption).foregroundStyle(MatchLensStyle.secondary)
            }
        } else { Text("Clip duration unavailable.").font(.caption).foregroundStyle(MatchLensStyle.secondary) }
    }
}
private enum ReplayFilter: String, CaseIterable, Identifiable {
    case all = "All", goals = "Goals", saves = "Saves", cards = "Cards"
    var id: String { rawValue }
}
#Preview { DataNotice(title: "Highlight metadata", message: "No media or sample match is loaded in this preview.") }
