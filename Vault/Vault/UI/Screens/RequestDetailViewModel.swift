import Foundation
import Observation

@Observable
final class RequestDetailViewModel {
    enum State: Equatable {
        case requestable
        case requesting
        case loading(progress: Double, detail: String?)
        case available
        case failed(String)
    }

    var state: State = .requestable
    var isWorking = false
    var shouldPollQueue = false

    @MainActor
    func request(_ item: RecommendationItem, env: AppEnvironment) async {
        guard let discover = env.discover else { return }
        isWorking = true
        state = .requesting
        do {
            let result = try await discover.request(item)
            if result.status == "already_exists" {
                state = .available
                shouldPollQueue = false
            } else {
                shouldPollQueue = true
                await refreshQueue(env: env, matching: item)
                if state == .requesting { state = .loading(progress: 0, detail: "Wartet auf Queue …") }
            }
        } catch {
            shouldPollQueue = false
            state = .failed("Anfrage fehlgeschlagen: \(error.localizedDescription)")
        }
        isWorking = false
    }

    @MainActor
    func refreshQueue(env: AppEnvironment, matching item: RecommendationItem) async {
        guard let discover = env.discover else { return }
        do {
            let queue = try await discover.queue()
            if let match = queue.bestMatch(for: item) {
                let progress = min(1, max(0, match.progress))
                if progress >= 0.999 {
                    state = .available
                    shouldPollQueue = false
                } else {
                    state = .loading(progress: progress, detail: match.displayDetail)
                    shouldPollQueue = true
                }
            }
        } catch {
            if shouldPollQueue {
                state = .failed("Queue konnte nicht geladen werden: \(error.localizedDescription)")
            }
        }
    }

    @MainActor
    func pollQueue(env: AppEnvironment, matching item: RecommendationItem) async {
        while shouldPollQueue {
            try? await Task.sleep(for: .seconds(5))
            if Task.isCancelled { return }
            await refreshQueue(env: env, matching: item)
        }
    }
}

private extension Array where Element == QueueItem {
    func bestMatch(for item: RecommendationItem) -> QueueItem? {
        first { queueItem in
            queueItem.type.caseInsensitiveCompare(item.type) == .orderedSame
                && queueItem.title.normalizedQueueTitle.contains(item.title.normalizedQueueTitle)
        } ?? first { queueItem in
            queueItem.title.normalizedQueueTitle.contains(item.title.normalizedQueueTitle)
        }
    }
}

private extension QueueItem {
    var displayDetail: String? {
        let percent = "\(Int(progress * 100))%"
        return [status, timeLeft, percent].compactMap { $0 }.joined(separator: " · ")
    }
}

private extension String {
    var normalizedQueueTitle: String {
        folding(options: [.caseInsensitive, .diacriticInsensitive], locale: .current)
            .replacingOccurrences(of: "[^a-z0-9]+", with: " ", options: .regularExpression)
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }
}
