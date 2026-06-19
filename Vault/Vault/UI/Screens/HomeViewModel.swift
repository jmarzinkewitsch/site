import Foundation
import Observation

@Observable
final class HomeViewModel {
    var resume: [BaseItemDto] = []
    var nextUp: [BaseItemDto] = []
    var seasonPosterURLsByEpisodeID: [String: String] = [:]
    var seasonBackdropURLsByEpisodeID: [String: String] = [:]
    var latestMovies: [BaseItemDto] = []
    var latestSeries: [BaseItemDto] = []
    var errorMessage: String?
    var isLoading = false

    var isEmpty: Bool {
        resume.isEmpty && nextUp.isEmpty && latestMovies.isEmpty && latestSeries.isEmpty
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
        let seasonArtwork = await loadSeasonArtworkURLs(for: nextUp, library: library)
        seasonPosterURLsByEpisodeID = seasonArtwork.posterURLs
        seasonBackdropURLsByEpisodeID = seasonArtwork.backdropURLs
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

    private func loadSeasonArtworkURLs(
        for items: [BaseItemDto],
        library: VaultLibraryService
    ) async -> SeasonArtworkURLs {
        let seasonIDs = Set(items.compactMap(\.seasonId))
        guard !seasonIDs.isEmpty else { return SeasonArtworkURLs(posterURLs: [:], backdropURLs: [:]) }

        var posterURLsBySeasonID: [String: String] = [:]
        var backdropURLsBySeasonID: [String: String] = [:]
        for seasonID in seasonIDs {
            guard let season = try? await library.item(id: seasonID) else { continue }
            posterURLsBySeasonID[seasonID] = season.posterUrl
            backdropURLsBySeasonID[seasonID] = season.backdropUrl
        }

        let posterPairs: [(String, String)] = items.compactMap { item in
            guard let seasonID = item.seasonId,
                  let posterURL = posterURLsBySeasonID[seasonID]
            else { return nil }
            return (item.id, posterURL)
        }
        let posterURLs = Dictionary(uniqueKeysWithValues: posterPairs)

        let backdropPairs: [(String, String)] = items.compactMap { item in
            guard let seasonID = item.seasonId,
                  let backdropURL = backdropURLsBySeasonID[seasonID]
            else { return nil }
            return (item.id, backdropURL)
        }
        let backdropURLs = Dictionary(uniqueKeysWithValues: backdropPairs)

        return SeasonArtworkURLs(posterURLs: posterURLs, backdropURLs: backdropURLs)
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

private struct SeasonArtworkURLs: Sendable {
    let posterURLs: [String: String]
    let backdropURLs: [String: String]
}
