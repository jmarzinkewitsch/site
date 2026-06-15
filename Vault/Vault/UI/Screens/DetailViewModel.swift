import Foundation
import Observation

@Observable
final class DetailViewModel {
    var detail: BaseItemDto?
    var seasons: [BaseItemDto] = []
    var episodes: [BaseItemDto] = []
    var selectedSeasonID: String?
    var errorMessage: String?
    var isLoading = false
    var isSavingRating = false
    var isSavingWatched = false
    var ratingMessage: String?
    var watchedMessage: String?
    var watchedOverrides: [String: Bool] = [:]

    @MainActor
    func load(summary: BaseItemDto, env: AppEnvironment) async {
        guard let library = env.library else { return }
        isLoading = true
        defer { isLoading = false }
        do {
            detail = try await library.item(id: summary.id)
            if summary.kind == .series {
                seasons = try await library.seasons(seriesId: summary.id)
                if let first = seasons.first {
                    await selectSeason(first.id, seriesId: summary.id, env: env)
                }
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
            detail = try await library.item(id: itemId)
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
            detail = try await library.item(id: itemId)
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
}
