import Foundation
import Observation

/// Composition root: owns settings and the single vault-api client derived
/// from them. The tvOS app no longer talks directly to Jellyfin/Radarr/TMDB.
@Observable
final class AppEnvironment {
    enum Route: Equatable {
        case item(String)
        case play(String)
    }

    let settings = ServerSettings()
    private(set) var vault: VaultClient?
    var selectedTab = 0
    var pendingRoute: Route?

    init() { rebuildClient() }

    var isConfigured: Bool { vault != nil }

    func rebuildClient() {
        guard let url = settings.serverURL,
              let token = settings.token, !token.isEmpty
        else {
            vault = nil
            return
        }
        vault = VaultClient(config: .init(baseURL: url, bearerToken: token))
    }

    func signOut() {
        settings.clearCredentials()
        pendingRoute = nil
        rebuildClient()
    }

    func handle(_ url: URL) {
        guard url.scheme == "vault" else { return }
        let action = url.host
        let id = url.pathComponents.dropFirst().first
        guard let id, !id.isEmpty else { return }

        selectedTab = 0
        switch action {
        case "play": pendingRoute = .play(id)
        case "item": pendingRoute = .item(id)
        default: break
        }
    }

    var library: VaultLibraryService? { vault.map { VaultLibraryService(client: $0) } }
    var reporter: PlaybackReporter? { vault.map { PlaybackReporter(client: $0) } }

    func posterURL(for item: BaseItemDto, maxWidth: Int = 600) -> URL? {
        guard let raw = item.posterUrl else { return nil }
        return URL(string: raw)
    }

    func backdropURL(for item: BaseItemDto, maxWidth: Int = 1920) -> URL? {
        if let raw = item.backdropUrl, let url = URL(string: raw) { return url }
        return posterURL(for: item, maxWidth: maxWidth)
    }

    /// Builds everything the player needs for one item by asking vault-api for
    /// a fresh direct Jellyfin stream URL. The video bytes still flow from
    /// Jellyfin to the Apple TV; the app never sees Jellyfin credentials.
    func playerItem(for item: BaseItemDto, resume: Bool) async -> PlayerItem? {
        guard let vault else { return nil }
        let mediaSourceId = item.mediaSources?.first?.id
        let query = mediaSourceId.map { [URLQueryItem(name: "media_source_id", value: $0)] } ?? []
        guard let stream: StreamInfo = try? await vault.get("stream/\(item.id)", query: query),
              let url = URL(string: stream.url)
        else { return nil }

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
            durationSeconds: item.durationSeconds ?? stream.runtimeSeconds,
            badges: Format.badges(for: item.allMediaStreams)
        )
    }
}
