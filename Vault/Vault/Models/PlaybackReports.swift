import Foundation

/// 1 Jellyfin tick = 100 ns; 1 second = 10_000_000 ticks.
enum JellyfinTicks {
    static func from(seconds: Double) -> Int64 { Int64(seconds * 10_000_000) }
    static func toSeconds(_ ticks: Int64) -> Double { Double(ticks) / 10_000_000 }
}

struct PlaybackStartInfo: Encodable, Sendable {
    let itemId: String
    let mediaSourceId: String?
    let positionTicks: Int64
    let playMethod: String
    let canSeek: Bool

    init(itemId: String, mediaSourceId: String?, positionTicks: Int64) {
        self.itemId = itemId
        self.mediaSourceId = mediaSourceId
        self.positionTicks = positionTicks
        self.playMethod = "DirectStream"
        self.canSeek = true
    }

    enum CodingKeys: String, CodingKey {
        case itemId = "ItemId"
        case mediaSourceId = "MediaSourceId"
        case positionTicks = "PositionTicks"
        case playMethod = "PlayMethod"
        case canSeek = "CanSeek"
    }
}

struct PlaybackProgressInfo: Encodable, Sendable {
    let itemId: String
    let mediaSourceId: String?
    let positionTicks: Int64
    let isPaused: Bool
    let playMethod: String

    init(itemId: String, mediaSourceId: String?, positionTicks: Int64, isPaused: Bool) {
        self.itemId = itemId
        self.mediaSourceId = mediaSourceId
        self.positionTicks = positionTicks
        self.isPaused = isPaused
        self.playMethod = "DirectStream"
    }

    enum CodingKeys: String, CodingKey {
        case itemId = "ItemId"
        case mediaSourceId = "MediaSourceId"
        case positionTicks = "PositionTicks"
        case isPaused = "IsPaused"
        case playMethod = "PlayMethod"
    }
}

struct PlaybackStopInfo: Encodable, Sendable {
    let itemId: String
    let mediaSourceId: String?
    let positionTicks: Int64

    enum CodingKeys: String, CodingKey {
        case itemId = "ItemId"
        case mediaSourceId = "MediaSourceId"
        case positionTicks = "PositionTicks"
    }
}
