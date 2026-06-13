import Foundation

/// 1 Jellyfin tick = 100 ns; 1 second = 10_000_000 ticks. Still used where the
/// player reports positions in ticks before they are converted to seconds.
enum JellyfinTicks {
    static func from(seconds: Double) -> Int64 { Int64(seconds * 10_000_000) }
    static func toSeconds(_ ticks: Int64) -> Double { Double(ticks) / 10_000_000 }
}
