import Foundation
import Observation

@Observable
final class DetailViewModel {
    var detail: BaseItemDto?
    var headerBackdropURL: String?
    var seasons: [BaseItemDto] = []
    var episodes: [BaseItemDto] = []
    var selectedSeasonID: String?
    var errorMessage: String?
    var isLoading = false
    var isSavingRating = false
    var isSavingDetailedRating = false
    var isSavingWatched = false
    var ratingMessage: String?
    var detailedRatingMessage: String?
    var detailedRatingErrorMessage: String?
    var watchedMessage: String?
    var watchedOverrides: [String: Bool] = [:]

    @MainActor
    func load(summary: BaseItemDto, env: AppEnvironment) async {
        guard let library = env.library else { return }
        isLoading = true
        defer { isLoading = false }
        do {
            let loadedDetail = try await library.item(id: summary.id)
            detail = loadedDetail
            headerBackdropURL = await loadHeaderBackdropURL(for: loadedDetail, library: library)
            if let seriesId = seriesId(for: summary) {
                seasons = try await library.seasons(seriesId: seriesId)
                // For an episode, preselect its own season so the viewer lands in
                // the right list; otherwise start at the first season.
                let targetSeason = (summary.kind == .episode ? summary.seasonId : nil)
                    ?? seasons.first?.id
                if let targetSeason {
                    await selectSeason(targetSeason, seriesId: seriesId, env: env)
                }
            }
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    /// The series these episodes belong to: the item itself for a series, or the
    /// parent series for an episode.
    private func seriesId(for summary: BaseItemDto) -> String? {
        summary.kind == .series ? summary.id : summary.seriesId
    }

    @MainActor
    func refreshPlaybackState(summary: BaseItemDto, env: AppEnvironment) async {
        guard let library = env.library else { return }
        do {
            let loadedDetail = try await library.item(id: summary.id)
            detail = loadedDetail
            headerBackdropURL = await loadHeaderBackdropURL(for: loadedDetail, library: library)
            if let seriesId = seriesId(for: summary), let selectedSeasonID {
                episodes = try await library.episodes(seriesId: seriesId, seasonId: selectedSeasonID)
            }
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    @MainActor
    func setRating(_ rating: Double, itemId: String, env: AppEnvironment) async {
        guard let library = env.library else { return }
        isSavingRating = true
        defer { isSavingRating = false }
        do {
            try await library.setRating(itemId: itemId, rating: rating)
            let loadedDetail = try await library.item(id: itemId)
            detail = loadedDetail
            headerBackdropURL = await loadHeaderBackdropURL(for: loadedDetail, library: library)
            ratingMessage = "Bewertung gespeichert"
            errorMessage = nil
        } catch {
            ratingMessage = nil
            errorMessage = error.localizedDescription
        }
    }

    @MainActor
    func setWatched(_ watched: Bool, itemId: String, env: AppEnvironment) async {
        guard let library = env.library else { return }
        let previous = watchedOverrides[itemId]
        watchedOverrides[itemId] = watched
        isSavingWatched = true
        defer { isSavingWatched = false }
        do {
            try await library.setWatched(itemId: itemId, watched: watched)
            let loadedDetail = try await library.item(id: itemId)
            detail = loadedDetail
            headerBackdropURL = await loadHeaderBackdropURL(for: loadedDetail, library: library)
            watchedOverrides[itemId] = detail?.isPlayed
            watchedMessage = watched ? "Als gesehen markiert" : "Als ungesehen markiert"
            errorMessage = nil
        } catch {
            watchedOverrides[itemId] = previous
            watchedMessage = nil
            errorMessage = error.localizedDescription
        }
    }

    @MainActor
    func saveDetailedRating(_ snapshot: VaultRatingSnapshot, item: BaseItemDto, markWatched: Bool, env: AppEnvironment) async {
        guard let library = env.library else { return }
        let previousWatchedOverride = watchedOverrides[item.id]
        if markWatched {
            watchedOverrides[item.id] = true
        }
        isSavingDetailedRating = true
        defer { isSavingDetailedRating = false }
        do {
            try await library.saveRatingSnapshot(itemId: item.id, snapshot: snapshot)
            if markWatched {
                try await library.setWatched(itemId: item.id, watched: true)
            }
            let loadedDetail = try await library.item(id: item.id)
            detail = loadedDetail
            headerBackdropURL = await loadHeaderBackdropURL(for: loadedDetail, library: library)
            watchedOverrides[item.id] = detail?.isPlayed
            detailedRatingMessage = markWatched ? "Bewertung gespeichert und als gesehen markiert" : "Bewertung gespeichert"
            detailedRatingErrorMessage = nil
            errorMessage = nil
        } catch {
            watchedOverrides[item.id] = previousWatchedOverride
            detailedRatingMessage = nil
            detailedRatingErrorMessage = "Bewertung konnte nicht gespeichert werden: \(error.localizedDescription)"
        }
    }

    @MainActor
    func setEpisodeWatched(_ watched: Bool, episode: BaseItemDto, env: AppEnvironment) async {
        guard let library = env.library else { return }
        let previous = watchedOverrides[episode.id]
        watchedOverrides[episode.id] = watched
        do {
            try await library.setWatched(itemId: episode.id, watched: watched)
            if let selectedSeasonID, let seriesId = episode.seriesId {
                episodes = try await library.episodes(seriesId: seriesId, seasonId: selectedSeasonID)
                watchedOverrides[episode.id] = episodes.first(where: { $0.id == episode.id })?.isPlayed
            }
            errorMessage = nil
        } catch {
            watchedOverrides[episode.id] = previous
            errorMessage = error.localizedDescription
        }
    }

    @MainActor
    func selectSeason(_ seasonId: String, seriesId: String, env: AppEnvironment) async {
        guard let library = env.library else { return }
        selectedSeasonID = seasonId
        do {
            episodes = try await library.episodes(seriesId: seriesId, seasonId: seasonId)
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func loadHeaderBackdropURL(for item: BaseItemDto, library: VaultLibraryService) async -> String? {
        guard item.kind == .episode else { return item.backdropUrl }

        if let seasonID = item.seasonId,
           let season = try? await library.item(id: seasonID),
           let seasonBackdropURL = season.backdropUrl {
            return seasonBackdropURL
        }

        if let seriesID = item.seriesId,
           let series = try? await library.item(id: seriesID),
           let seriesBackdropURL = series.backdropUrl {
            return seriesBackdropURL
        }

        return item.backdropUrl
    }
}
