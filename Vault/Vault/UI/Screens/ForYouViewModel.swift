import Foundation
import Observation

@Observable
final class ForYouViewModel {
    var shelves: [RecommendationShelf] = []
    var llmUsed = false
    var errorMessage: String?
    var isLoading = false
    var selectedProfile = "both"

    /// Outcome of the last request, shown to the user as an alert.
    var requestMessage: String?
    /// Ids currently being requested, so cards can show a spinner.
    private(set) var pendingRequestIDs: Set<String> = []

    var isEmpty: Bool { shelves.allSatisfy { $0.items.isEmpty } }
    var visibleShelves: [RecommendationShelf] { shelves.filter { $0.profile == selectedProfile } }
    var profileTabs: [(id: String, title: String)] { shelves.map { ($0.profile, $0.title) } }

    func isRequesting(_ item: RecommendationItem) -> Bool {
        pendingRequestIDs.contains(item.id)
    }

    @MainActor
    func load(env: AppEnvironment) async {
        guard let discover = env.discover else { return }
        isLoading = true
        defer { isLoading = false }
        do {
            let response = try await discover.recommendations()
            shelves = response.shelves
            llmUsed = response.llmUsed
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    @MainActor
    func request(_ item: RecommendationItem, env: AppEnvironment) async {
        guard let discover = env.discover, !pendingRequestIDs.contains(item.id) else { return }
        pendingRequestIDs.insert(item.id)
        defer { pendingRequestIDs.remove(item.id) }
        do {
            let result = try await discover.request(item)
            requestMessage = result.status == "already_exists"
                ? "\(result.title) ist bereits angefragt."
                : "\(result.title) wird angefragt und heruntergeladen."
        } catch {
            requestMessage = "Anfrage fehlgeschlagen: \(error.localizedDescription)"
        }
    }
}
