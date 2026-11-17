import SwiftUI
import AVKit

struct MatchReplayView: View {
    @Environment(\.dismiss) private var dismiss
    @State private var selectedFilter: ReplayFilter = .all
    @State private var playbackTime: Double = 134
    @State private var showVideoUnavailable = false
    @State private var player: AVPlayer?

    private let duration: Double
    private let events = ReplayEvent.samples
    private let clock = Timer.publish(every: 0.25, on: .main, in: .common).autoconnect()

    // No sample video is bundled yet. Supply a local file URL and its duration later.
    // Remote URLs are deliberately ignored in this frontend implementation.
    init(localVideoURL: URL? = nil, duration: Double = 720) {
        self.duration = duration.isFinite && duration > 0 ? duration : 720
        let localPlayer: AVPlayer?
        if let url = localVideoURL, url.isFileURL {
            localPlayer = AVPlayer(url: url)
        } else {
            localPlayer = nil
        }
        _player = State(initialValue: localPlayer)
        _playbackTime = State(initialValue: min(134, self.duration))
    }

    private var filteredEvents: [ReplayEvent] {
        selectedFilter == .all ? events : events.filter { $0.kind == selectedFilter }
    }

    var body: some View {
        ZStack {
            ReplayStyle.background.ignoresSafeArea()
            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    HStack(spacing: 0) {
                        Button { dismiss() } label: {
                            Image(systemName: "chevron.left")
                                .font(.system(size: 15, weight: .bold))
                                .frame(width: 18, height: 44, alignment: .leading)
                                .frame(minWidth: 32, alignment: .leading)
                                .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                        .accessibilityLabel("Back")
                        Text("Match Replay")
                            .font(.system(size: 22, weight: .bold))
                            .accessibilityAddTraits(.isHeader)
                    }

                    playerArea.padding(.top, 16)
                    playbackTimeline.padding(.top, 22)

                    Text("Jump to a moment")
                        .font(.system(size: 20, weight: .bold))
                        .accessibilityAddTraits(.isHeader)
                        .padding(.top, 20)

                    HStack(spacing: 7) {
                        ForEach(ReplayFilter.allCases) { filter in
                            Button { selectedFilter = filter } label: {
                                Text(filter.rawValue)
                                    .font(.system(size: 11, weight: .bold))
                                    .foregroundColor(selectedFilter == filter ? .white : ReplayStyle.secondary)
                                    .frame(maxWidth: .infinity)
                                    .frame(height: 30)
                                    .background(selectedFilter == filter ? ReplayStyle.blue : ReplayStyle.track)
                                    .clipShape(Capsule())
                                    .frame(minHeight: 44)
                                    .contentShape(Rectangle())
                            }
                            .buttonStyle(.plain)
                            .accessibilityAddTraits(selectedFilter == filter ? .isSelected : [])
                        }
                    }
                    .padding(.top, 4)

                    VStack(spacing: 8) {
                        ForEach(filteredEvents) { event in
                            Button { seek(to: event.seconds) } label: {
                                VStack(alignment: .leading, spacing: 2) {
                                    Text("\(timeLabel(event.seconds))  \(event.kind.eventLabel)")
                                        .font(.system(size: 13, weight: .bold))
                                        .foregroundColor(ReplayStyle.primary)
                                    Text(event.title)
                                        .font(.system(size: 13))
                                        .foregroundColor(ReplayStyle.secondary)
                                }
                                .padding(.horizontal, 12)
                                .padding(.vertical, 9)
                                .frame(maxWidth: .infinity, minHeight: 50, alignment: .leading)
                                .background(ReplayStyle.card)
                                .clipShape(RoundedRectangle(cornerRadius: 16))
                                .contentShape(RoundedRectangle(cornerRadius: 16))
                            }
                            .buttonStyle(.plain)
                            .accessibilityHint("Seeks to \(timeLabel(event.seconds))")
                        }
                    }
                    .padding(.top, 6)
                }
                .foregroundColor(ReplayStyle.primary)
                .frame(maxWidth: 440, alignment: .leading)
                .padding(.horizontal, 22)
                .padding(.top, 20)
                .padding(.bottom, 32)
                .frame(maxWidth: .infinity)
            }
        }
        .preferredColorScheme(.dark)
        .navigationBarBackButtonHidden(true)
        .toolbar(.hidden, for: .navigationBar)
        .alert("Video not available yet", isPresented: $showVideoUnavailable) {
            Button("OK", role: .cancel) { }
        } message: {
            Text("You can still explore the timeline and select match events. A local highlight video can be added later.")
        }
        .onAppear { seek(to: playbackTime) }
        .onDisappear { player?.pause() }
        .onReceive(clock) { _ in
            // Read actual playback time only; never simulate playback without video.
            guard let player = player, player.timeControlStatus == .playing else { return }
            let seconds = player.currentTime().seconds
            if seconds.isFinite { playbackTime = min(max(0, seconds), duration) }
        }
    }

    private var playerArea: some View {
        ZStack(alignment: .bottomLeading) {
            ReplayStyle.player
            if let player = player {
                VideoPlayer(player: player)
            } else {
                Button { showVideoUnavailable = true } label: {
                    Image(systemName: "play.fill")
                        .font(.system(size: 42))
                        .foregroundColor(ReplayStyle.primary)
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel("Play match replay")

                Text("CITY BLUES  3 : 2  REDS")
                    .font(.system(size: 14, weight: .bold))
                    .padding(24)
                    .allowsHitTesting(false)
            }
        }
        .frame(height: 194)
        .clipShape(RoundedRectangle(cornerRadius: 21))
        .overlay(alignment: .top) {
            ReplayStyle.blue.frame(height: 7).clipShape(Capsule())
        }
    }

    private var playbackTimeline: some View {
        VStack(spacing: 0) {
            HStack {
                Text(timeLabel(playbackTime))
                    .font(.system(size: 13, weight: .bold))
                Spacer()
                Text(timeLabel(duration))
                    .font(.system(size: 13))
                    .foregroundColor(ReplayStyle.secondary)
            }
            .monospacedDigit()

            GeometryReader { geometry in
                ZStack(alignment: .leading) {
                    Capsule().fill(ReplayStyle.track).frame(height: 7)
                    Capsule().fill(ReplayStyle.blue)
                        .frame(width: geometry.size.width * CGFloat(playbackTime / duration), height: 7)
                    // Use all events here so filtering never removes timeline markers.
                    ForEach(events) { event in
                        RoundedRectangle(cornerRadius: 1.5)
                            .fill(event.kind.markerColor)
                            .frame(width: 4, height: 16)
                            .offset(x: max(0, geometry.size.width - 4) * CGFloat(min(event.seconds / duration, 1)))
                    }
                }
                .frame(height: 32)
                .frame(maxWidth: .infinity)
                .contentShape(Rectangle())
                .gesture(DragGesture(minimumDistance: 0).onChanged { value in
                    guard geometry.size.width > 0 else { return }
                    seek(to: Double(value.location.x / geometry.size.width) * duration)
                })
            }
            .frame(height: 32)
            .accessibilityElement(children: .ignore)
            .accessibilityLabel("Playback position")
            .accessibilityValue("\(timeLabel(playbackTime)) of \(timeLabel(duration))")
            .accessibilityAdjustableAction { direction in
                switch direction {
                case .increment: seek(to: playbackTime + 10)
                case .decrement: seek(to: playbackTime - 10)
                @unknown default: break
                }
            }
        }
    }

    private func seek(to seconds: Double) {
        playbackTime = min(max(0, seconds), duration)
        player?.seek(to: CMTime(seconds: playbackTime, preferredTimescale: 600), toleranceBefore: .zero, toleranceAfter: .zero)
    }

    private func timeLabel(_ seconds: Double) -> String {
        let total = Int(max(0, seconds))
        return String(format: "%02d:%02d", total / 60, total % 60)
    }
}

private enum ReplayFilter: String, CaseIterable, Identifiable {
    case all = "All", goals = "Goals", saves = "Saves", cards = "Cards"
    var id: String { rawValue }
    var eventLabel: String {
        switch self {
        case .all: return "ALL"
        case .goals: return "GOAL"
        case .saves: return "SAVE"
        case .cards: return "CARD"
        }
    }
    var markerColor: Color {
        switch self {
        case .goals: return Color(red: 166 / 255, green: 1, blue: 0)
        case .saves, .all: return ReplayStyle.blue
        case .cards: return Color(red: 1, green: 0.25, blue: 0.2)
        }
    }
}

private struct ReplayEvent: Identifiable {
    let seconds: Double
    let kind: ReplayFilter
    let title: String
    var id: Double { seconds }

    static let samples = [
        ReplayEvent(seconds: 134, kind: .goals, title: "Opening goal"),
        ReplayEvent(seconds: 278, kind: .saves, title: "Goalkeeper's reflex save"),
        ReplayEvent(seconds: 382, kind: .cards, title: "Yellow card awarded"),
        ReplayEvent(seconds: 616, kind: .goals, title: "Winning goal")
    ]
}

private enum ReplayStyle {
    static let background = Color(red: 12 / 255, green: 16 / 255, blue: 32 / 255)
    static let player = Color(red: 23 / 255, green: 45 / 255, blue: 75 / 255)
    static let card = Color(red: 26 / 255, green: 38 / 255, blue: 61 / 255)
    static let track = Color(red: 30 / 255, green: 48 / 255, blue: 76 / 255)
    static let blue = Color(red: 40 / 255, green: 120 / 255, blue: 240 / 255)
    static let primary = Color(red: 240 / 255, green: 243 / 255, blue: 251 / 255)
    static let secondary = Color(red: 166 / 255, green: 185 / 255, blue: 209 / 255)
}

#Preview {
    NavigationStack {
        MatchReplayView()
    }
}
