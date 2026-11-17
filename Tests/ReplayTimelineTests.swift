import Foundation

// A small offline executable; it does not need SwiftUI, AVKit or an iOS Simulator.
// Compile this together with MatchLensApp/Views/Replay/ReplayTimeline.swift.
@main
struct ReplayTimelineTests {
    static func main() {
        let invalidDurations: [Double] = [0, -1, .nan, .infinity, -.infinity, .greatestFiniteMagnitude]
        for value in invalidDurations {
            precondition(ReplayTimeline.duration(value) == 720, "Invalid duration must use a safe default")
        }
        precondition(ReplayTimeline.duration(480) == 480)
        precondition(ReplayTimeline.duration(0.5) == 0.5)
        precondition(ReplayTimeline.position(-1, duration: 480) == 0)
        precondition(ReplayTimeline.position(600, duration: 480) == 480)
        precondition(ReplayTimeline.position(134, duration: 480) == 134)
        for value in [Double.nan, .infinity, -.infinity] {
            precondition(ReplayTimeline.position(value, duration: 480) == 0)
            precondition(ReplayTimeline.label(value) == "--:--")
        }
        precondition(ReplayTimeline.position(999, duration: .nan) == 720)
        precondition(ReplayTimeline.label(-1) == "00:00")
        precondition(ReplayTimeline.label(134.9) == "02:14")
        precondition(ReplayTimeline.label(720) == "12:00")
        precondition(ReplayTimeline.label(Double(Int.max)) == "--:--")
        precondition(ReplayTimeline.label(.greatestFiniteMagnitude) == "--:--")
        print("Replay timeline checks passed (23 assertions).")
    }
}
