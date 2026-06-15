import Foundation

struct VaultLibraryService: Sendable {
    let client: VaultClient

    func resumeItems(limit: Int = 12) async throws -> [BaseItemDto] {
        let items: [BaseItemDto] = try await client.get("library/continue")
        return Array(items.prefix(limit))
    }

    func nextUp(limit: Int = 12) async throws -> [BaseItemDto] {
        let items: [BaseItemDto] = try await client.get("library/nextup", query: [
            URLQueryItem(name: "limit", value: "\(limit)")
        ])
        return Array(items.prefix(limit))
    }

    /// Recently added shelf — hits the date-added "latest" endpoint, not the
    /// SortName-ordered list, so newly added titles actually show up.
    func latest(kind: ItemKind, limit: Int = 16) async throws -> [BaseItemDto] {
        try await client.get("library/latest", query: [
            URLQueryItem(name: "type", value: kind.rawValue),
            URLQueryItem(name: "limit", value: "\(limit)")
        ])
    }

    func items(kind: ItemKind, startIndex: Int, limit: Int = 100) async throws -> QueryResult<BaseItemDto> {
        let path = kind == .series ? "library/series" : "library/movies"
        let items: [BaseItemDto] = try await client.get(path, query: [
            URLQueryItem(name: "start", value: "\(startIndex)"),
            URLQueryItem(name: "limit", value: "\(limit)")
        ])
        let total = items.count < limit ? startIndex + items.count : startIndex + items.count + 1
        return QueryResult(items: items, totalRecordCount: total)
    }

    func item(id: String) async throws -> BaseItemDto {
        try await client.get("library/item/\(id)")
    }

    func nextEpisode(after itemId: String) async throws -> BaseItemDto? {
        try await client.get("library/item/\(itemId)/next-episode")
    }

    func setRating(itemId: String, rating: Double) async throws {
        try await client.post("library/item/\(itemId)/rating", body: VaultRatingUpdate(rating: rating))
    }

    func setWatched(itemId: String, watched: Bool) async throws {
        try await client.post("library/item/\(itemId)/watched", body: VaultWatchedUpdate(watched: watched))
    }

    func saveRatingSnapshot(itemId: String, snapshot: VaultRatingSnapshot) async throws {
        try await client.post("ratings/item/\(itemId)/snapshot", body: snapshot)
    }

    func seasons(seriesId: String) async throws -> [BaseItemDto] {
        try await client.get("library/series/\(seriesId)/seasons")
    }

    func episodes(seriesId: String, seasonId: String) async throws -> [BaseItemDto] {
        try await client.get("library/series/\(seriesId)/seasons/\(seasonId)/episodes")
    }
}

struct StreamSegment: Decodable, Hashable, Sendable {
    let type: String
    let start: Double
    let end: Double

    var title: String {
        type == "outro" ? "Abspann überspringen" : "Intro überspringen"
    }
}

struct StreamInfo: Decodable, Sendable {
    let url: String
    let container: String?
    let runtimeSeconds: Double?
    let segments: [StreamSegment]?
}

struct VaultProgressUpdate: Encodable {
    let positionSeconds: Double
    let isPaused: Bool
}

struct VaultRatingUpdate: Encodable {
    let rating: Double
}

struct VaultWatchedUpdate: Encodable {
    let watched: Bool
}

struct VaultRatingSnapshot: Encodable {
    let title: String
    let type: String
    let year: Int?
    let tmdbId: Int?
    let imdbId: String?
    let jannoRating: Double?
    let tannoRating: Double?
    let tannoFearFactor: Double?
}
