import Foundation

/// Search service for vault-api `/search?q=…`.
struct VaultSearchService: Sendable {
    let client: VaultClient

    func search(query: String) async throws -> [SearchItem] {
        let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return [] }
        return try await client.get("search", query: [URLQueryItem(name: "q", value: trimmed)])
    }
}
