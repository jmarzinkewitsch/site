import Foundation
import Observation

@Observable
final class RequestableDetailViewModel {
    enum RequestState: Equatable {
        case requestable
        case requesting
        case downloading(RequestQueueItem)
        case requestedWaiting
        case available(libraryId: String?)
    }

    var state: RequestState = .requestable
    var errorMessage: String?
    var requestMessage: String?

    var isBusy: Bool {
        if case .requesting = state { return true }
        return false
    }

    @MainActor
    func request(_ item: RecommendationItem, env: AppEnvironment) async {
        guard let discover = env.discover, !isBusy else { return }
        state = .requesting
        do {
            let result = try await discover.request(item)
            requestMessage = result.status == "already_exists"
                ? "Bereits angefragt"
                : "Anfrage gestartet"
            await refreshQueue(for: item, env: env)
            if case .requesting = state { state = .requestedWaiting }
            errorMessage = nil
        } catch {
            state = .requestable
            errorMessage = "Anfrage fehlgeschlagen: \(error.localizedDescription)"
        }
    }

    @MainActor
    func refreshQueue(for item: RecommendationItem, env: AppEnvironment) async {
        guard let discover = env.discover else { return }
        do {
            let queue = try await discover.queue()
            if let match = queue.first(where: { $0.matches(item) }) {
                state = .downloading(match)
            } else if case .downloading = state {
                state = .available(libraryId: await playableLibraryID(for: item, discover: discover))
            } else if case .requesting = state {
                state = .requestedWaiting
            }
            errorMessage = nil
        } catch {
            errorMessage = "Queue konnte nicht geladen werden: \(error.localizedDescription)"
        }
    }

    private func playableLibraryID(for item: RecommendationItem, discover: VaultDiscoverService) async -> String? {
        guard let response = try? await discover.recommendations(limit: 40) else { return nil }
        let match = response.shelves
            .flatMap(\.items)
            .first { candidate in
                candidate.isPlayable
                    && candidate.type.lowercased() == item.type.lowercased()
                    && candidate.title.normalizedQueueTitle == item.title.normalizedQueueTitle
            }
        return match?.libraryId
    }
}

private extension RequestQueueItem {
    func matches(_ item: RecommendationItem) -> Bool {
        type.lowercased() == item.type.lowercased()
            && title.normalizedQueueTitle == item.title.normalizedQueueTitle
    }
}

private extension String {
    var normalizedQueueTitle: String {
        folding(options: [.diacriticInsensitive, .caseInsensitive], locale: .current)
            .components(separatedBy: CharacterSet.alphanumerics.inverted)
            .filter { !$0.isEmpty }
            .joined(separator: " ")
    }
}
