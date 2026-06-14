import Foundation
import Observation

/// Composition root: owns settings and the single vault-api client derived
/// from them. The tvOS app no longer talks directly to Jellyfin/Radarr/TMDB.
@Observable
final class AppEnvironment {
    let settings = ServerSettings()
    private(set) var vault: VaultClient?
    var selectedTab: RootTab = .home
    var pendingDetailItem: BaseItemDto?
    var pendingPlayerItem: PlayerItem?
    /// Set when preparing playback fails before the player opens, so the UI can
    /// tell the user why nothing happened instead of silently doing nothing.
    var playbackError: String?

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
        rebuildClient()
    }

    var library: VaultLibraryService? { vault.map { VaultLibraryService(client: $0) } }
    var reporter: PlaybackReporter? { vault.map { PlaybackReporter(client: $0) } }

    @MainActor
    func handleOpenURL(_ url: URL) {
        guard url.scheme == "vault" else { return }
        let action = url.host
        let itemId = url.pathComponents.dropFirst().first
        guard let action, let itemId else { return }

        Task { @MainActor in
            await open(itemID: itemId, action: action)
        }
    }

    @MainActor
    private func open(itemID: String, action: String) async {
        guard let library else { return }
        do {
            let item = try await library.item(id: itemID)
            selectedTab = .home
            switch action {
            case "play":
                pendingPlayerItem = await playerItem(for: item, resume: item.resumePositionSeconds > 1)
            case "item":
                pendingDetailItem = item
            default:
                break
            }
        } catch {
            // Top Shelf deep links are best-effort; keep the app usable if the
            // referenced item disappeared or the server is temporarily offline.
        }
    }

    // Image URLs come fully built from vault-api, so there is no client-side
    // resizing knob — callers just ask for the poster or backdrop.
    func posterURL(for item: BaseItemDto) -> URL? {
        guard let raw = item.posterUrl else { return nil }
        return URL(string: raw)
    }

    func backdropURL(for item: BaseItemDto) -> URL? {
        if let raw = item.backdropUrl, let url = URL(string: raw) { return url }
        return posterURL(for: item)
    }

    /// Builds everything the player needs for one item by asking vault-api for
    /// a fresh direct Jellyfin stream URL. The video bytes still flow from
    /// Jellyfin to the Apple TV; the app never sees Jellyfin credentials.
    @MainActor
    func playerItem(for item: BaseItemDto, resume: Bool) async -> PlayerItem? {
        guard let vault else {
            playbackError = "Nicht mit vault-api verbunden."
            return nil
        }
        let mediaSourceId = item.mediaSources?.first?.id
        let query = mediaSourceId.map { [URLQueryItem(name: "media_source_id", value: $0)] } ?? []
        let stream: StreamInfo
        do {
            stream = try await vault.get("stream/\(item.id)", query: query)
        } catch {
            playbackError = "Stream konnte nicht geladen werden: \(error.localizedDescription)"
            return nil
        }
        guard let url = URL(string: stream.url) else {
            playbackError = "Der Server hat eine ungültige Stream-URL geliefert."
            return nil
        }

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
