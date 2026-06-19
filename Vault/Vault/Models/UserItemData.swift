import Foundation

struct UserItemDataDto: Decodable, Sendable {
    let playbackPositionTicks: Int64?
    let playCount: Int?
    let played: Bool?
    let playedPercentage: Double?

    enum CodingKeys: String, CodingKey {
        case playbackPositionTicks, playCount, played, playedPercentage
        case legacyPlaybackPositionTicks = "PlaybackPositionTicks"
        case legacyPlayCount = "PlayCount"
        case legacyPlayed = "Played"
        case legacyPlayedPercentage = "PlayedPercentage"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        playbackPositionTicks = try c.decodeIfPresent(Int64.self, forKey: .playbackPositionTicks)
            ?? c.decodeIfPresent(Int64.self, forKey: .legacyPlaybackPositionTicks)
        playCount = try c.decodeIfPresent(Int.self, forKey: .playCount)
            ?? c.decodeIfPresent(Int.self, forKey: .legacyPlayCount)
        played = try c.decodeIfPresent(Bool.self, forKey: .played)
            ?? c.decodeIfPresent(Bool.self, forKey: .legacyPlayed)
        playedPercentage = try c.decodeIfPresent(Double.self, forKey: .playedPercentage)
            ?? c.decodeIfPresent(Double.self, forKey: .legacyPlayedPercentage)
    }
}
