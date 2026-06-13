import Foundation
import Observation

/// Composition root: owns settings and the Jellyfin client/services derived
/// from them. Injected into the view tree via `.environment(_:)`.
@Observable
final class AppEnvironment {
    let settings = ServerSettings()
    private(set) var vault: VaultClient?
    var jellyfin: VaultClient? { vault }

    init() {
        rebuildClient()
    }

    var isConfigured: Bool { jellyfin != nil }

    func rebuildClient() {
        guard let url = settings.serverURL,
              let token = settings.token, !token.isEmpty
        else {
            vault = nil
            return
        }
        vault = VaultClient(config: .init(
            baseURL: url, token: token, userId: settings.userId ?? "vault", deviceId: settings.deviceId
        ))
    }

    func signOut() {
        settings.clearCredentials()
        rebuildClient()
    }

    var library: LibraryService? {
        vault.map { LibraryService(client: $0) }
    }

    var reporter: PlaybackReporter? {
        vault.map { PlaybackReporter(client: $0) }
    }

    // MARK: - URL helpers for views

    func posterURL(for item: BaseItemDto, maxWidth: Int = 600) -> URL? {
        item.posterURL
    }

    func backdropURL(for item: BaseItemDto, maxWidth: Int = 1920) -> URL? {
        item.backdropURL ?? item.posterURL
    }

    /// Builds everything the player needs for one item by asking vault-api for a fresh Jellyfin direct-stream URL.
    func playerItem(for item: BaseItemDto, resume: Bool) async -> PlayerItem? {
        guard let vault else { return nil }
        let mediaSourceId: String? = nil
        let info: StreamInfo
        do {
            info = try await vault.get("stream/\(item.id)")
        } catch {
            return nil
        }
        guard let url = URL(string: info.url) else { return nil }

        let subtitle: String?
        if item.kind == .episode {
            subtitle = [item.episodeCode, item.name].compactMap { $0 }.joined(separator: " · ")
        } else {
            subtitle = nil
        }
        return PlayerItem(
            itemId: item.id,
            mediaSourceId: mediaSourceId,
            title: item.kind == .episode ? (item.seriesName ?? item.name ?? "") : (item.name ?? ""),
            subtitle: subtitle,
            streamURL: url,
            httpHeaders: [:],
            startSeconds: resume ? item.resumePositionSeconds : 0,
            durationSeconds: info.runtimeSeconds ?? item.durationSeconds,
            badges: Format.badges(for: item.allMediaStreams)
        )
    }
}


private struct StreamInfo: Decodable {
    let url: String
    let container: String?
    let runtimeSeconds: Double?

    enum CodingKeys: String, CodingKey {
        case url, container
        case runtimeSeconds = "runtime_seconds"
    }
}
