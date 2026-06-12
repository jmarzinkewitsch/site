import Foundation
import Observation

@Observable
final class DetailViewModel {
    var detail: BaseItemDto?
    var seasons: [BaseItemDto] = []
    var episodes: [BaseItemDto] = []
    var selectedSeasonID: String?
    var errorMessage: String?

    @MainActor
    func load(summary: BaseItemDto, env: AppEnvironment) async {
        guard let library = env.library else { return }
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
