import Foundation
import Observation
import os
import TVServices

/// Composition root: owns settings and the single vault-api client derived
/// from them. The tvOS app no longer talks directly to Jellyfin/Radarr/TMDB.
@Observable
final class AppEnvironment {
    private static let logger = Logger(subsystem: "de.marzinkewitsch.Vault", category: "MediaURL")

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
        // The Top Shelf extension reads the same credentials from the shared
        // App Group, but tvOS caches its content and only re-runs the extension
        // when it is told the content changed. Without this, configuring the
        // server in-app leaves the Top Shelf stuck on its initial empty state.
        TVTopShelfContentProvider.topShelfContentDidChange()
    }

    func signOut() {
        settings.clearCredentials()
        rebuildClient()
    }

    var library: VaultLibraryService? { vault.map { VaultLibraryService(client: $0) } }
    var discover: VaultDiscoverService? { vault.map { VaultDiscoverService(client: $0) } }
    var search: VaultSearchService? { vault.map { VaultSearchService(client: $0) } }
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
    func open(itemID: String, action: String) async {
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
        return reachableMediaURL(from: raw)
    }

    func logoURL(for item: BaseItemDto) -> URL? {
        guard let raw = item.logoUrl else { return nil }
        return reachableMediaURL(from: raw)
    }

    func backdropURL(for item: BaseItemDto) -> URL? {
        if let raw = item.backdropUrl, let url = reachableMediaURL(from: raw) { return url }
        return posterURL(for: item)
    }

    func reachableMediaURL(from raw: String) -> URL? {
        guard let url = URL(string: raw) else { return nil }
        return reachableMediaURL(from: url)
    }

    func reachableMediaURLIfPresent(_ url: URL?) -> URL? {
        guard let url else { return nil }
        return reachableMediaURL(from: url)
    }

    func reachableMediaURL(from url: URL) -> URL {
        guard isDockerHost(url.host),
              let serverURL = settings.serverURL,
              let serverHost = serverURL.host,
              var components = URLComponents(url: url, resolvingAgainstBaseURL: false)
        else { return url }

        components.host = serverHost
        let rewritten = components.url ?? url
        Self.logger.info("Media URL rewrite: \(url.absoluteString, privacy: .public) -> \(rewritten.absoluteString, privacy: .public)")
        return rewritten
    }

    private func isDockerHost(_ host: String?) -> Bool {
        guard let host else { return false }
        return host == "host.docker.internal" || host.hasSuffix(".docker.internal")
    }

    /// Rewrites the host in a trickplay URL *template* that contains the
    /// literal string `{index}`. Because `{index}` makes the template an
    /// invalid URL, we temporarily substitute a sentinel digit, run the
    /// string through `reachableMediaURL`, then restore `{index}` by
    /// replacing the sentinel back — so the Docker-host rewrite works
    /// transparently without any special-casing for the template structure.
    func reachableMediaURLTemplate(_ template: String) -> String {
        // A sentinel that is unlikely to appear as a sheet index and is safe
        // in a URL path segment, yet distinct from any real index digit.
        let sentinel = "999999999"
        let filled = template.replacingOccurrences(of: "{index}", with: sentinel)
        guard let url = URL(string: filled) else { return template }
        let rewritten = reachableMediaURL(from: url)
        return rewritten.absoluteString.replacingOccurrences(of: sentinel, with: "{index}")
    }

    /// Builds everything the player needs for one item by asking vault-api for
    /// a fresh direct Jellyfin stream URL. The video bytes still flow from
    /// Jellyfin to the Apple TV; the app never sees Jellyfin credentials.
    @MainActor
    func playerItem(for item: BaseItemDto, resume: Bool, audioStreamIndex: Int? = nil) async -> PlayerItem? {
        guard let vault else {
            playbackError = "Nicht mit vault-api verbunden."
            return nil
        }
        let mediaSourceId = item.mediaSources?.first?.id
        var query = mediaSourceId.map { [URLQueryItem(name: "media_source_id", value: $0)] } ?? []
        if let audioStreamIndex {
            query.append(URLQueryItem(name: "audio_stream_index", value: "\(audioStreamIndex)"))
        }
        let stream: StreamInfo
        do {
            stream = try await vault.get("stream/\(item.id)", query: query)
        } catch {
            playbackError = "Stream konnte nicht geladen werden: \(error.localizedDescription)"
            return nil
        }
        guard let rawURL = URL(string: stream.url) else {
            playbackError = "Der Server hat eine ungültige Stream-URL geliefert."
            return nil
        }
        let url = reachableMediaURL(from: rawURL)

        let subtitle: String?
        if item.kind == .episode {
            subtitle = [item.episodeCode, item.name].compactMap { $0 }.joined(separator: " · ")
        } else {
            subtitle = nil
        }
        // Prefer the server's track list — it carries delivery URLs for
        // external (sidecar/OpenSubtitles) subs. Fall back to the embedded
        // streams in the item DTO for older vault-api versions.
        let subtitleTracks: [SubtitleTrackInfo]
        if let serverTracks = stream.subtitleTracks, !serverTracks.isEmpty {
            subtitleTracks = serverTracks.map { track in
                guard let url = track.deliveryURL else { return track }
                return SubtitleTrackInfo(
                    index: track.index,
                    language: track.language,
                    codec: track.codec,
                    displayTitle: track.displayTitle,
                    isExternal: track.isExternal,
                    deliveryURL: reachableMediaURL(from: url)
                )
            }
        } else {
            subtitleTracks = Self.textSubtitleTracks(from: item.allMediaStreams)
        }
        // Rewrite the trickplay template host if we're behind a Docker host.
        let trickplay: TrickplayInfo? = stream.trickplay.map { info in
            TrickplayInfo(
                interval: info.interval,
                tileWidth: info.tileWidth,
                tileHeight: info.tileHeight,
                thumbnailWidth: info.thumbnailWidth,
                thumbnailHeight: info.thumbnailHeight,
                thumbnailCount: info.thumbnailCount,
                tileURLTemplate: reachableMediaURLTemplate(info.tileURLTemplate)
            )
        }
        return PlayerItem(
            itemId: item.id,
            mediaSourceId: mediaSourceId,
            title: item.kind == .episode ? (item.seriesName ?? item.name ?? "") : (item.name ?? ""),
            subtitle: subtitle,
            type: item.type ?? "Movie",
            year: item.productionYear,
            tmdbId: item.tmdbId,
            imdbId: item.imdbId,
            streamURL: url,
            audioTracks: stream.audioTracks.isEmpty ? (item.audioTracks ?? []) : stream.audioTracks,
            selectedAudioTrackIndex: audioStreamIndex ?? stream.audioTracks.first?.index ?? item.audioTracks?.first?.index,
            subtitleTracks: subtitleTracks,
            selectedSubtitleTrackIndex: nil,
            httpHeaders: [:],
            startSeconds: resume ? item.resumePositionSeconds : 0,
            durationSeconds: item.durationSeconds ?? stream.runtimeSeconds,
            segments: stream.segments ?? [],
            badges: Format.badges(for: item.allMediaStreams),
            isTrailer: false,
            allowsPostPlayRating: true,
            trickplay: trickplay
        )
    }

    /// Filters Jellyfin's media stream list down to text-based subtitle
    /// tracks the engine can actually render. Bitmap subs (PGS/DVB/VobSub)
    /// are excluded — see SubtitleDecoder for the rendering caveat.
    private static func textSubtitleTracks(from streams: [MediaStream]) -> [SubtitleTrackInfo] {
        let supported: Set<String> = [
            "subrip", "srt", "ass", "ssa", "webvtt", "vtt", "mov_text", "text"
        ]
        return streams.compactMap { stream in
            guard stream.type?.lowercased() == "subtitle" else { return nil }
            guard let index = stream.index else { return nil }
            guard let codec = stream.codec?.lowercased(), supported.contains(codec) else { return nil }
            return SubtitleTrackInfo(
                index: index,
                language: stream.language,
                codec: stream.codec,
                displayTitle: stream.displayTitle
            )
        }
    }

    @MainActor
    func trailerPlayerItem(for item: BaseItemDto) async -> PlayerItem? {
        guard let library else {
            playbackError = "Nicht mit vault-api verbunden."
            return nil
        }
        let stream: TrailerStream
        do {
            stream = try await library.trailerStream(itemId: item.id)
        } catch {
            playbackError = "Trailer konnte nicht geladen werden: \(error.localizedDescription)"
            return nil
        }
        guard let rawURL = URL(string: stream.url) else {
            playbackError = "Der Server hat eine ungültige Trailer-URL geliefert."
            return nil
        }
        let url = reachableMediaURL(from: rawURL)
        return PlayerItem(
            itemId: "trailer-\(item.id)",
            mediaSourceId: nil,
            title: "Trailer: \(item.name ?? "—")",
            subtitle: nil,
            type: "Trailer",
            year: item.productionYear,
            tmdbId: item.tmdbId,
            imdbId: item.imdbId,
            streamURL: url,
            audioTracks: [],
            selectedAudioTrackIndex: nil,
            subtitleTracks: [],
            selectedSubtitleTrackIndex: nil,
            httpHeaders: [:],
            startSeconds: 0,
            durationSeconds: nil,
            segments: [],
            badges: [stream.container?.uppercased()].compactMap { $0 },
            isTrailer: true,
            allowsPostPlayRating: false,
            trickplay: nil
        )
    }

}
