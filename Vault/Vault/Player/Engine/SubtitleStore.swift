import Foundation

/// One decoded subtitle line with its display window in seconds.
struct SubtitleCue: Hashable {
    let startSeconds: Double
    let endSeconds: Double
    let text: String
}

/// Thread-safe, time-sorted bag of cues. The demux/decode side appends,
/// the sync timer queries by playback position.
///
/// After a backward seek, the demuxer may re-deliver cues we've already
/// stored. Dedupe checks the immediate neighbours by `(startSeconds, text)` —
/// good enough since cues are inserted in roughly increasing order.
final class SubtitleStore {
    private let lock = NSLock()
    private var cues: [SubtitleCue] = []

    func reset() {
        lock.lock(); defer { lock.unlock() }
        cues.removeAll(keepingCapacity: true)
    }

    func insert(_ cue: SubtitleCue) {
        guard !cue.text.isEmpty, cue.endSeconds > cue.startSeconds else { return }
        lock.lock(); defer { lock.unlock() }
        var lo = 0
        var hi = cues.count
        while lo < hi {
            let mid = (lo + hi) / 2
            if cues[mid].startSeconds < cue.startSeconds { lo = mid + 1 } else { hi = mid }
        }
        if lo > 0, cues[lo - 1].startSeconds == cue.startSeconds, cues[lo - 1].text == cue.text { return }
        if lo < cues.count, cues[lo].startSeconds == cue.startSeconds, cues[lo].text == cue.text { return }
        cues.insert(cue, at: lo)
    }

    /// Last cue with `startSeconds <= seconds`, but only if its window is
    /// still active (`seconds <= endSeconds`).
    func cue(at seconds: Double) -> SubtitleCue? {
        lock.lock(); defer { lock.unlock() }
        var lo = 0
        var hi = cues.count
        while lo < hi {
            let mid = (lo + hi) / 2
            if cues[mid].startSeconds <= seconds { lo = mid + 1 } else { hi = mid }
        }
        guard lo > 0 else { return nil }
        let candidate = cues[lo - 1]
        return seconds <= candidate.endSeconds ? candidate : nil
    }
}
