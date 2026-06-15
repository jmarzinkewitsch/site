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

    /// True once the title has appeared in the *arr queue, so we can tell
    /// "finished downloading and left the queue" apart from "not picked up yet".
    private var seenInQueue = false
    /// `already_exists` came back from /request — the title is in the *arr
    /// library already and may simply be imported (no active download).
    private var wasAlreadyExists = false
    /// Polls where the title was absent from the queue before it was ever seen.
    private var emptyPolls = 0
    /// ~15 s grace before an already-present title is treated as imported.
    private let emptyPollGrace = 3

    @MainActor
    func request(_ item: RecommendationItem, env: AppEnvironment) async {
        guard let discover = env.discover else { return }
        isWorking = true
        state = .requesting
        seenInQueue = false
        emptyPolls = 0
        do {
            let result = try await discover.request(item)
            // `already_exists` only means Radarr/Sonarr already has the title —
            // it may still be downloading — so poll the queue either way instead
            // of assuming it is ready to play.
            wasAlreadyExists = result.status == "already_exists"
            shouldPollQueue = true
            await refreshQueue(env: env, matching: item)
            if state == .requesting { state = .loading(progress: 0, detail: "Wartet auf Queue …") }
        } catch {
            shouldPollQueue = false
            state = .failed("Anfrage fehlgeschlagen: \(error.localizedDescription)")
        }
        isWorking = false
    }

    @MainActor
    func refreshQueue(env: AppEnvironment, matching item: RecommendationItem) async {
        guard let discover = env.discover else { return }
        let queue: [QueueItem]
        do {
            queue = try await discover.queue()
        } catch {
            if shouldPollQueue {
                shouldPollQueue = false
                state = .failed("Queue konnte nicht geladen werden: \(error.localizedDescription)")
            }
            return
        }

        if let match = queue.bestMatch(for: item) {
            seenInQueue = true
            emptyPolls = 0
            let progress = min(1, max(0, match.progress))
            if progress >= 0.999 {
                finishAvailable()
            } else {
                state = .loading(progress: progress, detail: match.displayDetail)
                shouldPollQueue = true
            }
        } else if shouldPollQueue {
            // Only react to an empty queue while a request is actually in flight.
            // On the initial detail-screen load (no request sent yet) the item
            // must stay requestable so the user can still press „Anfragen".
            if seenInQueue {
                // Was downloading and has now left the queue → import finished.
                finishAvailable()
            } else if wasAlreadyExists {
                // In the *arr library and not downloading; after a short grace,
                // treat it as imported and playable instead of polling forever.
                emptyPolls += 1
                if emptyPolls >= emptyPollGrace { finishAvailable() }
            } else {
                // Freshly requested but not in the queue yet — keep waiting for
                // the download client to pick it up.
                state = .loading(progress: 0, detail: "Angefragt – wartet auf Download …")
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

    @MainActor
    private func finishAvailable() {
        state = .available
        shouldPollQueue = false
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
