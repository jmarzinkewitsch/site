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
    /// Auth headers for the stream request (token never goes into the URL).
    let httpHeaders: [String: String]
    let startSeconds: Double
    let durationSeconds: Double?
    let badges: [String]

    var id: String { itemId }
}
