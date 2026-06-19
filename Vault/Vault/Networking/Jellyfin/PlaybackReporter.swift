import Foundation

/// Reports playback progress to vault-api. Session lifecycle calls are kept as
/// no-ops because vault-api's public contract intentionally exposes only the
/// progress endpoint to the app.
struct PlaybackReporter: Sendable {
    let client: VaultClient

    func started(itemId: String, mediaSourceId: String?, positionTicks: Int64) async { }

    func progress(itemId: String, mediaSourceId: String?, positionTicks: Int64, isPaused: Bool) async {
        try? await client.post(
            "library/item/\(itemId)/progress",
            body: VaultProgressUpdate(
                positionSeconds: Double(positionTicks) / 10_000_000,
                isPaused: isPaused
            )
        )
    }

    func stopped(itemId: String, mediaSourceId: String?, positionTicks: Int64) async {
        await progress(itemId: itemId, mediaSourceId: mediaSourceId, positionTicks: positionTicks, isPaused: true)
    }

    /// Marks the item as fully watched on the server.
    /// Called automatically near the end of playback so the item drops out of
    /// "Weiterschauen" without requiring the user to watch the last few seconds.
    func markWatched(itemId: String) async {
        try? await client.post(
            "library/item/\(itemId)/watched",
            body: VaultWatchedUpdate(watched: true)
        )
    }
}
