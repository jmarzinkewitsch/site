import Foundation
import Observation

@Observable
final class HomeViewModel {
    var resume: [BaseItemDto] = []
    var nextUp: [BaseItemDto] = []
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

        async let resumeTask = library.resumeItems()
        async let nextUpTask = library.nextUp()
        async let moviesTask = library.latest(kind: .movie)
        async let seriesTask = library.latest(kind: .series)

        do {
            (resume, nextUp, latestMovies, latestSeries) =
                try await (resumeTask, nextUpTask, moviesTask, seriesTask)
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func item(withID id: String) -> BaseItemDto? {
        for list in [resume, nextUp, latestMovies, latestSeries] {
            if let match = list.first(where: { $0.id == id }) { return match }
        }
        return nil
    }
}
