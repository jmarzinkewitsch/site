import Foundation
import Observation

/// Composition root: owns settings and the Jellyfin client/services derived
/// from them. Injected into the view tree via `.environment(_:)`.
@Observable
final class AppEnvironment {
    let settings = ServerSettings()
    private(set) var jellyfin: JellyfinClient?

    init() {
        rebuildClient()
    }

    var isConfigured: Bool { jellyfin != nil }

    func rebuildClient() {
        guard let url = settings.serverURL,
              let token = settings.token, !token.isEmpty,
              let userId = settings.userId, !userId.isEmpty
        else {
            jellyfin = nil
            return
        }
        jellyfin = JellyfinClient(config: .init(
            baseURL: url, token: token, userId: userId, deviceId: settings.deviceId
        ))
    }

    func signOut() {
        settings.clearCredentials()
        rebuildClient()
    }

    var library: LibraryService? {
        jellyfin.map { LibraryService(client: $0) }
    }

    var reporter: PlaybackReporter? {
        jellyfin.map { PlaybackReporter(client: $0) }
    }

    // MARK: - URL helpers for views

    func posterURL(for item: BaseItemDto, maxWidth: Int = 600) -> URL? {
        guard let base = settings.serverURL else { return nil }
        // Episodes without their own primary image fall back to the series poster.
        if let tag = item.imageTags?["Primary"] {
            return ImageURLBuilder.primary(baseURL: base, itemId: item.id, tag: tag, maxWidth: maxWidth)
        }
        if let seriesId = item.seriesId {
            return ImageURLBuilder.primary(baseURL: base, itemId: seriesId, tag: nil, maxWidth: maxWidth)
        }
        return ImageURLBuilder.primary(baseURL: base, itemId: item.id, tag: nil, maxWidth: maxWidth)
    }

    func backdropURL(for item: BaseItemDto, maxWidth: Int = 1920) -> URL? {
        guard let base = settings.serverURL else { return nil }
        if let tag = item.backdropImageTags?.first {
            return ImageURLBuilder.backdrop(baseURL: base, itemId: item.id, tag: tag, maxWidth: maxWidth)
        }
        // Episodes/seasons: use the series backdrop; last resort: poster.
        if let seriesId = item.seriesId {
            return ImageURLBuilder.backdrop(baseURL: base, itemId: seriesId, tag: nil, maxWidth: maxWidth)
        }
        return posterURL(for: item, maxWidth: maxWidth)
    }

    /// Builds everything the player needs for one item.
    func playerItem(for item: BaseItemDto, resume: Bool) -> PlayerItem? {
        guard let base = settings.serverURL, let token = settings.token else { return nil }
        let mediaSourceId = item.mediaSources?.first?.id
        guard let url = StreamURLBuilder.directStream(
            baseURL: base, itemId: item.id, token: token, mediaSourceId: mediaSourceId
        ) else { return nil }

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
            startSeconds: resume ? item.resumePositionSeconds : 0,
            durationSeconds: item.durationSeconds,
            badges: Format.badges(for: item.allMediaStreams)
        )
    }
}
