import Foundation

struct LibraryService: Sendable {
    let client: JellyfinClient

    private var userId: String { client.config.userId }

    private static let defaultFields = "Overview,Genres,MediaSources,PrimaryImageAspectRatio"

    /// Continue watching (partially played items).
    func resumeItems(limit: Int = 12) async throws -> [BaseItemDto] {
        let result: QueryResult<BaseItemDto> = try await client.get(
            "Users/\(userId)/Items/Resume",
            query: [
                URLQueryItem(name: "limit", value: "\(limit)"),
                URLQueryItem(name: "mediaTypes", value: "Video"),
                URLQueryItem(name: "fields", value: Self.defaultFields),
            ]
        )
        return result.items
    }

    /// Next unwatched episodes of followed series.
    func nextUp(limit: Int = 12) async throws -> [BaseItemDto] {
        let result: QueryResult<BaseItemDto> = try await client.get(
            "Shows/NextUp",
            query: [
                URLQueryItem(name: "userId", value: userId),
                URLQueryItem(name: "limit", value: "\(limit)"),
                URLQueryItem(name: "fields", value: Self.defaultFields),
            ]
        )
        return result.items
    }

    /// Recently added. Note: this endpoint returns a bare array, not a QueryResult.
    func latest(kind: ItemKind, limit: Int = 16) async throws -> [BaseItemDto] {
        try await client.get(
            "Users/\(userId)/Items/Latest",
            query: [
                URLQueryItem(name: "includeItemTypes", value: kind.rawValue),
                URLQueryItem(name: "limit", value: "\(limit)"),
            ]
        )
    }

    /// Paged library browse for the Movies/Series grids.
    func items(kind: ItemKind, startIndex: Int, limit: Int = 100) async throws -> QueryResult<BaseItemDto> {
        try await client.get(
            "Items",
            query: [
                URLQueryItem(name: "userId", value: userId),
                URLQueryItem(name: "includeItemTypes", value: kind.rawValue),
                URLQueryItem(name: "recursive", value: "true"),
                URLQueryItem(name: "sortBy", value: "SortName"),
                URLQueryItem(name: "sortOrder", value: "Ascending"),
                URLQueryItem(name: "startIndex", value: "\(startIndex)"),
                URLQueryItem(name: "limit", value: "\(limit)"),
                URLQueryItem(name: "imageTypeLimit", value: "1"),
            ]
        )
    }

    /// Full item detail including MediaSources/MediaStreams and UserData.
    func item(id: String) async throws -> BaseItemDto {
        try await client.get("Users/\(userId)/Items/\(id)")
    }

    func seasons(seriesId: String) async throws -> [BaseItemDto] {
        let result: QueryResult<BaseItemDto> = try await client.get(
            "Shows/\(seriesId)/Seasons",
            query: [URLQueryItem(name: "userId", value: userId)]
        )
        return result.items
    }

    func episodes(seriesId: String, seasonId: String) async throws -> [BaseItemDto] {
        let result: QueryResult<BaseItemDto> = try await client.get(
            "Shows/\(seriesId)/Episodes",
            query: [
                URLQueryItem(name: "userId", value: userId),
                URLQueryItem(name: "seasonId", value: seasonId),
                URLQueryItem(name: "fields", value: "Overview,MediaSources"),
            ]
        )
        return result.items
    }
}
