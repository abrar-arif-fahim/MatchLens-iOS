import SwiftUI

struct MatchReplayView: View {
    @Environment(\.dismiss) private var dismiss
    let detail: MatchDetail
    let highlight: HighlightRecord
    @State private var selectedFilter: ReplayFilter = .all
    @State private var selectedEventID: String?
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
    private var selectedSeconds: Double? { rows.first { $0.eventId == selectedEventID }?.seconds }
    var body: some View {
        ZStack {
            MatchLensStyle.background.ignoresSafeArea()
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    HStack {
                        Button { dismiss() } label: { Image(systemName: "chevron.left").frame(width: 44, height: 44).contentShape(Rectangle()) }
                            .accessibilityLabel("Back")
                        Text("Match Replay").font(.title2.bold()).accessibilityAddTraits(.isHeader)
                    }.buttonStyle(.plain)
                    Button { showVideoUnavailable = true } label: {
                        VStack(alignment: .leading, spacing: 16) {
                            Image(systemName: "video.slash.fill").font(.system(size: 42))
                                .frame(maxWidth: .infinity)
                            Text(detail.card.title).font(.headline)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        .foregroundStyle(.white)
                        .padding(24)
                        .frame(maxWidth: .infinity, minHeight: 194)
                        .background(Color(red: 23 / 255, green: 45 / 255, blue: 75 / 255))
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain).clipShape(RoundedRectangle(cornerRadius: 21))
                    .overlay(alignment: .top) {
                        MatchLensStyle.blue.frame(height: 7).clipShape(Capsule()).allowsHitTesting(false)
                    }
                    .accessibilityLabel("Video unavailable for \(detail.card.title)")
                    .accessibilityHint("Explains why this highlight can’t be played")
                    if detail.card.match.isDemo { Text("DEMO — fictional match and marker positions").foregroundStyle(.orange) }
                    Text(highlight.title).font(.title3.bold())
                    Text("Metadata only • No authorized video is available").font(.caption).foregroundStyle(MatchLensStyle.secondary)
                    metadataTimeline
                    Text("Select a moment").font(.title2.bold()).accessibilityAddTraits(.isHeader)
                    AdaptiveActionRow {
                        ForEach(ReplayFilter.allCases) { filter in
                            Button {
                                selectedFilter = filter
                                if selectedSeconds == nil { selectedEventID = nil }
                            } label: {
                                Text(filter.rawValue).font(.caption.bold())
                                    .frame(maxWidth: .infinity, minHeight: 44)
                                    .background(selectedFilter == filter ? MatchLensStyle.blue : MatchLensStyle.card)
                                    .clipShape(Capsule())
                            }.buttonStyle(.plain).accessibilityAddTraits(selectedFilter == filter ? .isSelected : [])
                        }
                    }
                    if rows.isEmpty {
                        DataNotice(title: "No moments to show", message: selectedFilter == .all
                            ? "There are no published timeline markers for this highlight." : "Choose another filter to see more moments.")
                    }
                    ForEach(rows, id: \.eventId) { marker in
                        if let event = detail.events.first(where: { $0.id == marker.eventId }) {
                            Button { selectedEventID = marker.eventId } label: {
                                VStack(alignment: .leading, spacing: 6) {
                                    Text(ReplayTimeline.label(marker.seconds) + " • " + event.label).font(.headline)
                                    Text("Football clock: " + event.clock).font(.caption).foregroundStyle(MatchLensStyle.secondary)
                                }.padding(14).frame(maxWidth: .infinity, alignment: .leading)
                                    .background(MatchLensStyle.card).clipShape(RoundedRectangle(cornerRadius: 16))
                            }.buttonStyle(.plain)
                                .accessibilityAddTraits(selectedEventID == marker.eventId ? .isSelected : [])
                                .accessibilityHint("Selects timeline metadata; no video is played.")
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
                    .accessibilityElement(children: .ignore)
                    .accessibilityLabel("Highlight timeline")
                    .accessibilityValue(selectedSeconds.map { "\(ReplayTimeline.label($0)) of \(ReplayTimeline.label(duration))" }
                        ?? "No marker selected. Duration \(ReplayTimeline.label(duration))")
                GeometryReader { geometry in
                    ZStack(alignment: .leading) {
                        Capsule().fill(MatchLensStyle.card).frame(height: 7)
                        Capsule().fill(MatchLensStyle.blue)
                            .frame(width: geometry.size.width * CGFloat((selectedSeconds ?? 0) / duration), height: 7)
                        ForEach(rows, id: \.eventId) { marker in
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
