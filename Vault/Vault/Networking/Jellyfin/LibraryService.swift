import Foundation

struct LibraryService: Sendable {
    let client: VaultClient

    func resumeItems(limit: Int = 12) async throws -> [BaseItemDto] {
        let items: [BaseItemDto] = try await client.get("library/continue")
        return Array(items.prefix(limit))
    }

    func nextUp(limit: Int = 12) async throws -> [BaseItemDto] { [] }

    func latest(kind: ItemKind, limit: Int = 16) async throws -> [BaseItemDto] {
        let path = kind == .series ? "library/series" : "library/movies"
        return try await client.get(path, query: [URLQueryItem(name: "start", value: "0"), URLQueryItem(name: "limit", value: "\(limit)")])
    }

    func items(kind: ItemKind, startIndex: Int, limit: Int = 100) async throws -> QueryResult<BaseItemDto> {
        let path = kind == .series ? "library/series" : "library/movies"
        let rows: [BaseItemDto] = try await client.get(path, query: [URLQueryItem(name: "start", value: "\(startIndex)"), URLQueryItem(name: "limit", value: "\(limit)")])
        return QueryResult(items: rows, totalRecordCount: rows.count < limit ? startIndex + rows.count : nil)
    }

    func item(id: String) async throws -> BaseItemDto { try await client.get("library/item/\(id)") }
    func seasons(seriesId: String) async throws -> [BaseItemDto] { [] }
    func episodes(seriesId: String, seasonId: String) async throws -> [BaseItemDto] { [] }
}
