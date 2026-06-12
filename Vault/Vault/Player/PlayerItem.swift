import Foundation

/// Everything the player screen needs to play one item.
struct PlayerItem: Identifiable, Hashable {
    let itemId: String
    let mediaSourceId: String?
    let title: String
    let subtitle: String?
    let streamURL: URL
    let startSeconds: Double
    let durationSeconds: Double?
    let badges: [String]

    var id: String { itemId }
}
