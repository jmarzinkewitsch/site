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
}
