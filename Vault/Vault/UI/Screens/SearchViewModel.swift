import Foundation
import Observation

@Observable
final class SearchViewModel {
    var query = ""
    var results: [SearchItem] = []
    var errorMessage: String?
    var isLoading = false

    private var searchTask: Task<Void, Never>?

    var hasQuery: Bool { !query.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }

    @MainActor
    func queryChanged(env: AppEnvironment) {
        searchTask?.cancel()
        let currentQuery = query
        guard !currentQuery.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            results = []
            errorMessage = nil
            isLoading = false
            return
        }

        searchTask = Task { [currentQuery] in
            try? await Task.sleep(for: .milliseconds(300))
            guard !Task.isCancelled else { return }
            await search(currentQuery, env: env)
        }
    }

    @MainActor
    func search(_ term: String, env: AppEnvironment) async {
        guard let search = env.search else { return }
        isLoading = true
        defer { isLoading = false }
        do {
            let fetched = try await search.search(query: term)
            guard term == query else { return }
            results = fetched
            errorMessage = nil
        } catch is CancellationError {
            // Ignore superseded searches.
        } catch {
            errorMessage = error.localizedDescription
            results = []
        }
    }
}
