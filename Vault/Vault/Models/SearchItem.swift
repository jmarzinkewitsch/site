import Foundation

/// One hit from vault-api `/search?q=…`, combining owned library items and
/// TMDB discover results. snake_case → camelCase is handled by VaultClient.
struct SearchItem: Decodable, Identifiable, Hashable, Sendable {
    let title: String
    let type: String          // "Movie" | "Series"
    let year: Int?
    let posterUrl: String?
    let source: String        // "library" | "discover"
    let status: String        // "playable" | "requestable"
    let libraryId: String?
    let tmdbId: Int?

    var id: String {
        if let libraryId { return "library:\(libraryId)" }
        if let tmdbId { return "tmdb:\(type):\(tmdbId)" }
        return "\(source):\(type):\(title):\(year.map(String.init) ?? "")"
    }

    var isPlayable: Bool { status == "playable" }
    var isRequestable: Bool { status == "requestable" }

    var requestItem: RecommendationItem {
        RecommendationItem(
            id: id,
            title: title,
            type: type,
            year: year,
            overview: nil,
            posterUrl: posterUrl,
            backdropUrl: nil,
            score: 0,
            reason: "Suchtreffer",
            status: status,
            libraryId: libraryId,
            tmdbId: tmdbId,
            communityRating: nil,
            criticRating: nil,
            matchScore: nil,
            jannoScore: nil,
            tannoScore: nil,
            fearFactor: nil,
            profile: nil,
            categoryTags: []
        )
    }
}
