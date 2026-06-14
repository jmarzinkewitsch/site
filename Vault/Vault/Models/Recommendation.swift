import Foundation

/// Decodes vault-api's `/recommend` response. snake_case → camelCase is handled
/// by the client's `.convertFromSnakeCase` decoder.
struct RecommendationResponse: Decodable, Sendable {
    let shelves: [RecommendationShelf]
    let llmUsed: Bool
}

struct RecommendationShelf: Decodable, Identifiable, Sendable {
    let id: String
    let title: String
    let profile: String
    let items: [RecommendationItem]
}

struct RecommendationItem: Decodable, Identifiable, Hashable, Sendable {
    let id: String
    let title: String
    let type: String          // "Movie" | "Series"
    let year: Int?
    let overview: String?
    let posterUrl: String?
    let backdropUrl: String?
    let score: Double
    let reason: String
    let status: String        // "playable" | "requestable"
    let libraryId: String?
    let tmdbId: Int?
    let communityRating: Double?  // 0–10 (≈ IMDB / TMDB vote)
    let criticRating: Double?     // 0–100 (≈ RT %)
    let matchScore: Int?
    let jannoScore: Int?
    let tannoScore: Int?
    let fearFactor: Int?
    let profile: String?
    let categoryTags: [String]

    var isPlayable: Bool { status == "playable" }
    var isRequestable: Bool { status == "requestable" }

    static func == (lhs: RecommendationItem, rhs: RecommendationItem) -> Bool { lhs.id == rhs.id }
    func hash(into hasher: inout Hasher) { hasher.combine(id) }
}

/// Result of a POST /request/{movie,series}.
struct RequestResult: Decodable, Sendable {
    let ok: Bool
    let status: String        // "added" | "already_exists"
    let title: String
    let detail: String?
}

/// One item from GET /request/queue.
struct QueueItem: Decodable, Identifiable, Hashable, Sendable {
    let title: String
    let type: String          // "Movie" | "Series"
    let progress: Double      // 0...1
    let status: String?
    let timeLeft: String?

    var id: String { "\(type):\(title)" }
}
