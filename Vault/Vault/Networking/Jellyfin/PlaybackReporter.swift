import Foundation

struct PlaybackReporter: Sendable {
    let client: VaultClient

    struct ProgressBody: Encodable {
        let positionSeconds: Double
        let isPaused: Bool
        enum CodingKeys: String, CodingKey {
            case positionSeconds = "position_seconds"
            case isPaused = "is_paused"
        }
    }

    func started(itemId: String, mediaSourceId: String?, positionTicks: Int64) async {
        await progress(itemId: itemId, mediaSourceId: mediaSourceId, positionTicks: positionTicks, isPaused: false)
    }

    func progress(itemId: String, mediaSourceId: String?, positionTicks: Int64, isPaused: Bool) async {
        try? await client.post(
            "library/item/\(itemId)/progress",
            body: ProgressBody(positionSeconds: Double(positionTicks) / 10_000_000, isPaused: isPaused)
        )
    }

    func stopped(itemId: String, mediaSourceId: String?, positionTicks: Int64) async {
        await progress(itemId: itemId, mediaSourceId: mediaSourceId, positionTicks: positionTicks, isPaused: true)
    }
}
