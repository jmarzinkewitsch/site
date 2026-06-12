import Foundation

/// Reports playback sessions back to Jellyfin so progress and watched state
/// stay in sync. All calls are fire-and-forget: a failed report must never
/// interrupt playback.
struct PlaybackReporter: Sendable {
    let client: JellyfinClient

    func started(itemId: String, mediaSourceId: String?, positionTicks: Int64) async {
        try? await client.post(
            "Sessions/Playing",
            body: PlaybackStartInfo(itemId: itemId, mediaSourceId: mediaSourceId, positionTicks: positionTicks)
        )
    }

    func progress(itemId: String, mediaSourceId: String?, positionTicks: Int64, isPaused: Bool) async {
        try? await client.post(
            "Sessions/Playing/Progress",
            body: PlaybackProgressInfo(
                itemId: itemId, mediaSourceId: mediaSourceId,
                positionTicks: positionTicks, isPaused: isPaused
            )
        )
    }

    func stopped(itemId: String, mediaSourceId: String?, positionTicks: Int64) async {
        try? await client.post(
            "Sessions/Playing/Stopped",
            body: PlaybackStopInfo(itemId: itemId, mediaSourceId: mediaSourceId, positionTicks: positionTicks)
        )
    }
}
