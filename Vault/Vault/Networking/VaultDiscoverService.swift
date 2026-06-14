import Foundation

/// Recommendations ("Für dich") and add-to-library requests. Talks only to
/// vault-api, which orchestrates TMDB/Radarr/Sonarr/Claude behind the scenes.
struct VaultDiscoverService: Sendable {
    let client: VaultClient

    func recommendations(limit: Int = 12) async throws -> RecommendationResponse {
        try await client.get("recommend", query: [
            URLQueryItem(name: "limit", value: "\(limit)")
        ])
    }

    func request(_ item: RecommendationItem) async throws -> RequestResult {
        guard let tmdbId = item.tmdbId else {
            throw JellyfinError.invalidURL
        }
        let path = item.type.lowercased() == "series" ? "request/series" : "request/movie"
        return try await client.post(path, body: TmdbRequestBody(tmdbId: tmdbId))
    }

    func queue() async throws -> [RequestQueueItem] {
        try await client.get("request/queue")
    }
}

private struct TmdbRequestBody: Encodable {
    let tmdbId: Int  // encoded as tmdb_id via the client's snake_case strategy
}
