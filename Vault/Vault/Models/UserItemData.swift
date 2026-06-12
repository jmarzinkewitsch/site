import Foundation

struct UserItemDataDto: Decodable, Sendable {
    let playbackPositionTicks: Int64?
    let playCount: Int?
    let played: Bool?
    let playedPercentage: Double?

    enum CodingKeys: String, CodingKey {
        case playbackPositionTicks = "PlaybackPositionTicks"
        case playCount = "PlayCount"
        case played = "Played"
        case playedPercentage = "PlayedPercentage"
    }
}
