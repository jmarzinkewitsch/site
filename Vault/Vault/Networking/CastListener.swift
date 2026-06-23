import Foundation
import Observation
import os

/// The single non-server-side piece of "Cast to Apple TV". When the kiosk
/// casts a film it POSTs to vault-api, which (1) has Home Assistant wake this
/// Apple TV and launch the Vault app and (2) stashes a short-lived pending
/// play command. This listener polls `/cast/appletv/pending` and, when a
/// command is waiting, opens the *existing* player path with the Jellyfin
/// item id — resume position still comes from Jellyfin like every other play.
///
/// The pending store on the server is consume-once: a successful GET clears it,
/// so we never re-open the same film twice.
@MainActor
@Observable
final class CastListener {
    private static let logger = Logger(subsystem: "de.marzinkewitsch.Vault", category: "Cast")

    /// How often we re-check for a pending command while in the foreground.
    private static let pollInterval: Duration = .seconds(5)

    private let env: AppEnvironment
    private var pollTask: Task<Void, Never>?

    init(env: AppEnvironment) {
        self.env = env
    }

    /// Called once at launch and on every transition back to the foreground.
    /// Fetches the pending command immediately, then keeps a lightweight poll
    /// running until `stop()` (i.e. the app leaves the foreground).
    func start() {
        guard pollTask == nil else { return }
        pollTask = Task { [weak self] in
            while !Task.isCancelled {
                await self?.checkOnce()
                do {
                    try await Task.sleep(for: Self.pollInterval)
                } catch {
                    break // cancelled
                }
            }
        }
    }

    /// Stops the background poll. Safe to call when not running.
    func stop() {
        pollTask?.cancel()
        pollTask = nil
    }

    /// One pending check. Reuses the vault-api client/bearer token the app
    /// already holds. On a non-nil item id it opens the existing player.
    private func checkOnce() async {
        guard let vault = env.vault else { return }
        let pending: CastPending
        do {
            pending = try await vault.get("cast/appletv/pending")
        } catch {
            // Best-effort: a missing/offline backend just means "nothing to do".
            Self.logger.debug("Cast pending poll failed: \(error.localizedDescription, privacy: .public)")
            return
        }
        guard let itemId = pending.itemId, !itemId.isEmpty else { return }
        Self.logger.info("Cast pending: opening item \(itemId, privacy: .public)")
        await env.open(itemID: itemId, action: "play")
    }
}

/// Response of `GET /cast/appletv/pending`. `VaultClient` decodes snake_case,
/// so `item_id`/`created_at` map onto these camelCase properties.
struct CastPending: Decodable, Sendable {
    let itemId: String?
    let createdAt: String?
}
