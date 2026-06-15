import Foundation

/// Everything the player screen needs to play one item.
struct PlayerItem: Identifiable, Hashable {
    let itemId: String
    let mediaSourceId: String?
    let title: String
    let subtitle: String?
    let type: String
    let year: Int?
    let tmdbId: Int?
    let imdbId: String?
    let streamURL: URL
    let audioTracks: [AudioTrackInfo]
    let selectedAudioTrackIndex: Int?
    /// Auth headers for the stream request (token never goes into the URL).
    let httpHeaders: [String: String]
    let startSeconds: Double
    let durationSeconds: Double?
    let segments: [StreamSegment]
    let badges: [String]
    let isTrailer: Bool
    let allowsPostPlayRating: Bool

    var id: String { itemId }
}
