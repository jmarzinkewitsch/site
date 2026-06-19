import Foundation
import Observation

@Observable
final class HomeViewModel {
    var resume: [BaseItemDto] = []
    var nextUp: [BaseItemDto] = []
    var seasonBackdropURLsByEpisodeID: [String: String] = [:]
    var latestMovies: [BaseItemDto] = []
    var topRated: [BaseItemDto] = []
    var seasonal: [BaseItemDto] = []
    var discover: [BaseItemDto] = []
    var errorMessage: String?
    var isLoading = false

    /// Max entries in the merged Continue/Next-Up shelf.
    private let continueLimit = 6

    var isEmpty: Bool {
        resume.isEmpty && nextUp.isEmpty && latestMovies.isEmpty
            && topRated.isEmpty && seasonal.isEmpty && discover.isEmpty
    }

    /// Season-driven shelf title.
    var seasonalTitle: String {
        let month = Calendar.current.component(.month, from: Date())
        switch month {
        case 10: return "Gruselnacht"
        case 12: return "Winterzauber"
        case 6, 7, 8: return "Sommerkino"
        case 3, 4, 5: return "Frühlingsgefühle"
        default: return "Entdecken"
        }
    }

    /// Genre filter for the seasonal shelf (bilingual DE/EN).
    var seasonalGenres: [String] {
        let month = Calendar.current.component(.month, from: Date())
        switch month {
        case 10: return ["Horror", "Thriller"]
        case 12: return ["Family", "Familie", "Fantasy", "Animation"]
        case 6, 7, 8: return ["Adventure", "Abenteuer", "Action", "Comedy", "Komödie"]
        case 3, 4, 5: return ["Romance", "Liebesfilm", "Comedy", "Komödie"]
        default: return []
        }
    }

    /// Merged "Weiterschauen" shelf: in-progress items first, then the next
    /// episode of started series — deduplicated per series (or per movie) so an
    /// in-progress episode and that same series\'s next episode never both
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
        async let topRatedTask = loadShelf { try await library.shelf(sort: "top_rated", limit: 16) }
        async let discoverTask = loadShelf { try await library.shelf(sort: "random", unplayed: true, limit: 16) }
        let genres = seasonalGenres
        async let seasonalTask = loadShelf { try await library.shelf(sort: "random", genres: genres, limit: 16) }

        let results = await [resumeTask, nextUpTask, moviesTask, topRatedTask, discoverTask, seasonalTask]
        resume = results[0].items
        nextUp = results[1].items
        seasonBackdropURLsByEpisodeID = await loadSeasonBackdropURLs(for: nextUp, library: library)
        latestMovies = results[2].items
        topRated = results[3].items
        discover = results[4].items
        seasonal = results[5].items

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
        for list in [resume, nextUp, latestMovies, topRated, seasonal, discover] {
            if let match = list.first(where: { $0.id == id }) { return match }
        }
        return nil
    }
}

private struct ShelfResult: Sendable {
    let items: [BaseItemDto]
    let errorMessage: String?
}
