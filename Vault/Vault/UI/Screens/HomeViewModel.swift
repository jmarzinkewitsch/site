import Foundation
import Observation

@Observable
final class HomeViewModel {
    var resume: [BaseItemDto] = []
    var nextUp: [BaseItemDto] = []
    var seasonBackdropURLsByEpisodeID: [String: String] = [:]
    var latestMovies: [BaseItemDto] = []
    var latestSeries: [BaseItemDto] = []
    var errorMessage: String?
    var isLoading = false

    /// Max entries in the merged Continue/Next-Up shelf.
    private let continueLimit = 6

    var isEmpty: Bool {
        resume.isEmpty && nextUp.isEmpty && latestMovies.isEmpty && latestSeries.isEmpty
    }

    /// Merged "Weiterschauen" shelf: in-progress items first, then the next
    /// episode of started series — deduplicated per series (or per movie) so an
    /// in-progress episode and that same series' next episode never both
    /// appear, and capped at `continueLimit`.
    var continueWatching: [BaseItemDto] {
        var seen = Set<String>()
        var combined: [BaseItemDto] = []
        for item in resume + nextUp {
            let key = dedupKey(for: item)
            guard !seen.contains(key) else { continue }
            seen.insert(key)
            combined.append(item)
            if combined.count >= continueLimit { break }
        }
        return combined
    }

    /// One entry per series (for episodes) or per item (for movies).
    private func dedupKey(for item: BaseItemDto) -> String {
        if item.kind == .episode, let seriesID = item.seriesId {
            return "series:\(seriesID)"
        }
        return "item:\(item.id)"
    }

    @MainActor
    func load(env: AppEnvironment) async {
        guard let library = env.library else { return }
        isLoading = true
        defer { isLoading = false }

        async let resumeTask = loadShelf { try await library.resumeItems() }
        async let nextUpTask = loadShelf { try await library.nextUp() }
        async let moviesTask = loadShelf { try await library.latest(kind: .movie) }
        async let seriesTask = loadShelf { try await library.latest(kind: .series) }

        let results = await [resumeTask, nextUpTask, moviesTask, seriesTask]
        resume = results[0].items
        nextUp = results[1].items
        seasonBackdropURLsByEpisodeID = await loadSeasonBackdropURLs(for: nextUp, library: library)
        latestMovies = results[2].items
        latestSeries = results[3].items

        let failures = results.compactMap(\.errorMessage)
        errorMessage = isEmpty ? failures.first : nil
    }

    private func loadShelf(_ operation: @Sendable () async throws -> [BaseItemDto]) async -> ShelfResult {
        do {
            return ShelfResult(items: try await operation(), errorMessage: nil)
        } catch {
            return ShelfResult(items: [], errorMessage: error.localizedDescription)
        }
    }

    /// Season backdrops keyed by episode id — landscape artwork for next-up
    /// episodes (which often lack their own backdrop) and for the stage.
    private func loadSeasonBackdropURLs(
        for items: [BaseItemDto],
        library: VaultLibraryService
    ) async -> [String: String] {
        let seasonIDs = Set(items.compactMap(\.seasonId))
        guard !seasonIDs.isEmpty else { return [:] }

        var backdropURLsBySeasonID: [String: String] = [:]
        for seasonID in seasonIDs {
            guard let season = try? await library.item(id: seasonID) else { continue }
            backdropURLsBySeasonID[seasonID] = season.backdropUrl
        }

        let pairs: [(String, String)] = items.compactMap { item in
            guard let seasonID = item.seasonId,
                  let backdropURL = backdropURLsBySeasonID[seasonID]
            else { return nil }
            return (item.id, backdropURL)
        }
        return Dictionary(uniqueKeysWithValues: pairs)
    }

    func item(withID id: String) -> BaseItemDto? {
        for list in [resume, nextUp, latestMovies, latestSeries] {
            if let match = list.first(where: { $0.id == id }) { return match }
        }
        return nil
    }
}

private struct ShelfResult: Sendable {
    let items: [BaseItemDto]
    let errorMessage: String?
}
