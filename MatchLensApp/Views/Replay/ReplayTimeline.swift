import Foundation

// Keep timeline arithmetic safe before converting seconds to Int or CMTime.
enum ReplayTimeline {
    static func duration(_ seconds: Double) -> Double {
        // CMTime uses signed 64-bit ticks; the player uses 600 ticks per second.
        guard seconds.isFinite, seconds > 0, seconds < Double(Int64.max) / 600 else {
            return 720
        }
        return seconds
    }

    static func position(_ seconds: Double, duration: Double) -> Double {
        guard seconds.isFinite else { return 0 }
        return min(max(0, seconds), self.duration(duration))
    }

    static func label(_ seconds: Double) -> String {
        guard seconds.isFinite, seconds < Double(Int.max) else { return "--:--" }
        let total = Int(max(0, seconds))
        let minutes = String(total / 60)
        let remainder = String(total % 60)
        return (minutes.count < 2 ? "0" : "") + minutes + ":"
            + (remainder.count < 2 ? "0" : "") + remainder
    }
}
