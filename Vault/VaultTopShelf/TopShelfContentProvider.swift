import Foundation
import TVServices

final class TopShelfContentProvider: TVTopShelfContentProvider {
    private let loader = TopShelfLoader()

    override func loadTopShelfContent(completionHandler: @escaping (TVTopShelfContent?) -> Void) {
        Task {
            let items = await loader.loadItems()
            guard !items.isEmpty else {
                completionHandler(nil)
                return
            }
            completionHandler(TVTopShelfCarouselContent(style: .details, items: items))
        }
    }
}

private struct TopShelfLoader {
    func loadItems() async -> [TVTopShelfCarouselItem] {
        guard let config = TopShelfConfiguration.load() else { return [] }
        let client = TopShelfClient(config: config)

        do {
            async let continueItems = client.getItems("library/continue")
            async let latestMovies = client.getItems("library/latest", query: [
                URLQueryItem(name: "type", value: "Movie"),
                URLQueryItem(name: "limit", value: "8")
            ])
            async let latestSeries = client.getItems("library/latest", query: [
                URLQueryItem(name: "type", value: "Series"),
                URLQueryItem(name: "limit", value: "8")
            ])

            let movies = try await latestMovies
            let series = try await latestSeries
            let seriesEpisodes = await resolveLatestUnwatchedEpisodes(for: series, client: client)
            let latestItems = movies + seriesEpisodes
            let merged = try await curated(continueItems: continueItems, latestItems: latestItems)
            let top = Array(merged.prefix(10))
            let trailers = await trailerURLs(for: top, client: client)
            return top.compactMap {
                makeCarouselItem(from: $0, serverURL: config.baseURL, trailerURL: trailers[$0.id])
            }
        } catch {
            return []
        }
    }

    private func resolveLatestUnwatchedEpisodes(
        for seriesItems: [TopShelfLibraryItem],
        client: TopShelfClient
    ) async -> [TopShelfLibraryItem] {
        await withTaskGroup(of: TopShelfLibraryItem?.self) { group in
            for series in seriesItems {
                group.addTask {
                    await latestUnwatchedEpisode(for: series, client: client) ?? series
                }
            }

            var resolved: [TopShelfLibraryItem] = []
            for await item in group {
                if let item { resolved.append(item) }
            }
            return resolved
        }
    }

    private func latestUnwatchedEpisode(
        for series: TopShelfLibraryItem,
        client: TopShelfClient
    ) async -> TopShelfLibraryItem? {
        do {
            let seasons = try await client.getItems("library/series/\(series.id)/seasons")
            let episodes = try await withThrowingTaskGroup(of: [TopShelfLibraryItem].self) { group in
                for season in seasons {
                    group.addTask {
                        try await client.getItems("library/series/\(series.id)/seasons/\(season.id)/episodes")
                    }
                }

                var allEpisodes: [TopShelfLibraryItem] = []
                for try await seasonEpisodes in group {
                    allEpisodes.append(contentsOf: seasonEpisodes)
                }
                return allEpisodes
            }

            return episodes
                .filter { !$0.isPlayed }
                .sorted(by: TopShelfLibraryItem.isLaterEpisode)
                .first
        } catch {
            return nil
        }
    }

    /// Best-effort parallel lookup of trailer stream URLs. Items without a
    /// trailer (or whose request fails) are simply omitted, so the carousel
    /// falls back to the hero image for those.
    private func trailerURLs(
        for items: [TopShelfLibraryItem],
        client: TopShelfClient
    ) async -> [String: URL] {
        await withTaskGroup(of: (String, URL?).self) { group in
            for item in items {
                group.addTask { (item.id, await client.trailerURL(itemId: item.id)) }
            }
            var result: [String: URL] = [:]
            for await (id, url) in group {
                if let url { result[id] = url }
            }
            return result
        }
    }

    private func curated(continueItems: [TopShelfLibraryItem], latestItems: [TopShelfLibraryItem]) -> [TopShelfLibraryItem] {
        var seen = Set<String>()
        return (continueItems + latestItems).filter { item in
            guard !seen.contains(item.id) else { return false }
            seen.insert(item.id)
            return item.heroURL != nil
        }
    }

    private func makeCarouselItem(
        from item: TopShelfLibraryItem,
        serverURL: URL,
        trailerURL: URL?
    ) -> TVTopShelfCarouselItem? {
        guard let rawImageURL = item.heroURL else { return nil }
        // vault-api may hand back artwork URLs pointing at the Docker-internal
        // host (e.g. host.docker.internal). The Apple TV can't reach that, so —
        // mirroring the main app's rewrite — swap the host for the reachable
        // server host. Without this the carousel cards have no artwork and the
        // Top Shelf renders empty even though the API calls all succeed.
        let imageURL = reachableImageURL(rawImageURL, serverURL: serverURL)
        let carouselItem = TVTopShelfCarouselItem(identifier: item.id)
        // Title is shown by tvOS for the currently displayed/focused item; for
        // episodes use the series name so the show is identifiable.
        carouselItem.title = item.displayTitle
        carouselItem.summary = item.overview
        carouselItem.genre = item.genres?.prefix(3).joined(separator: " · ")
        if let duration = item.durationSeconds {
            carouselItem.duration = duration
        }
        carouselItem.setImageURL(imageURL, for: .screenScale1x)
        // Apple-TV-app-style auto-playing preview. tvOS plays this after the
        // hero image once the item is focused; falls back to the image when no
        // trailer is available. Docker-internal hosts are rewritten too.
        if let trailerURL {
            carouselItem.previewVideoURL = reachableImageURL(trailerURL, serverURL: serverURL)
        }
        carouselItem.displayAction = TVTopShelfAction(url: URL(string: "vault://item/\(item.id)")!)
        if item.isPlayable {
            carouselItem.playAction = TVTopShelfAction(url: URL(string: "vault://play/\(item.id)")!)
        }
        return carouselItem
    }

    /// Rewrites Docker-internal artwork hosts to the reachable server host,
    /// keeping scheme, port and path intact. Non-Docker URLs pass through.
    private func reachableImageURL(_ url: URL, serverURL: URL) -> URL {
        guard let host = url.host,
              host == "host.docker.internal" || host.hasSuffix(".docker.internal"),
              let serverHost = serverURL.host,
              var components = URLComponents(url: url, resolvingAgainstBaseURL: false)
        else { return url }

        components.host = serverHost
        return components.url ?? url
    }
}

private struct TopShelfConfiguration: Sendable {
    static let appGroupIdentifier = "group.de.marzinkewitsch.vault"

    let baseURL: URL
    let bearerToken: String

    static func load() -> TopShelfConfiguration? {
        let defaults = UserDefaults(suiteName: appGroupIdentifier) ?? .standard
        guard var rawURL = defaults.string(forKey: "vault.serverURL")?.trimmingCharacters(in: .whitespacesAndNewlines),
              !rawURL.isEmpty,
              let token = defaults.string(forKey: "vault.token"),
              !token.isEmpty
        else { return nil }
        if !rawURL.contains("://") { rawURL = "http://" + rawURL }
        while rawURL.hasSuffix("/") { rawURL.removeLast() }
        guard let baseURL = URL(string: rawURL) else { return nil }
        return TopShelfConfiguration(baseURL: baseURL, bearerToken: token)
    }
}

private actor TopShelfClient {
    private let config: TopShelfConfiguration
    private let session: URLSession
    private let decoder: JSONDecoder

    init(config: TopShelfConfiguration) {
        self.config = config
        let sessionConfig = URLSessionConfiguration.default
        sessionConfig.timeoutIntervalForRequest = 3
        sessionConfig.timeoutIntervalForResource = 3
        session = URLSession(configuration: sessionConfig)
        decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
    }

    func getItems(_ path: String, query: [URLQueryItem] = []) async throws -> [TopShelfLibraryItem] {
        let cleanPath = path.hasPrefix("/") ? String(path.dropFirst()) : path
        guard var components = URLComponents(url: config.baseURL.appendingPathComponent(cleanPath), resolvingAgainstBaseURL: false) else {
            return []
        }
        components.queryItems = query.isEmpty ? nil : query
        guard let url = components.url else { return [] }

        var request = URLRequest(url: url)
        request.setValue("Bearer \(config.bearerToken)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Accept")

        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse, 200..<300 ~= http.statusCode else { return [] }
        return try decoder.decode([TopShelfLibraryItem].self, from: data)
    }

    /// Best-effort trailer stream lookup; returns nil when the item has no
    /// trailer, the request fails, or the URL is unusable.
    func trailerURL(itemId: String) async -> URL? {
        guard var components = URLComponents(
            url: config.baseURL.appendingPathComponent("library/item/\(itemId)/trailer-stream"),
            resolvingAgainstBaseURL: false
        ) else { return nil }
        components.queryItems = nil
        guard let url = components.url else { return nil }

        var request = URLRequest(url: url)
        request.setValue("Bearer \(config.bearerToken)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Accept")

        guard let (data, response) = try? await session.data(for: request),
              let http = response as? HTTPURLResponse, 200..<300 ~= http.statusCode,
              let stream = try? decoder.decode(TopShelfTrailerStream.self, from: data)
        else { return nil }
        return URL(string: stream.url)
    }
}

private struct TopShelfTrailerStream: Decodable, Sendable {
    let url: String
}

private struct TopShelfLibraryItem: Decodable, Sendable {
    let id: String
    let title: String?
    let name: String?
    let type: String?
    let overview: String?
    let genres: [String]?
    let posterUrl: String?
    let backdropUrl: String?
    let seriesName: String?
    let runtimeSeconds: Double?
    let resumeSeconds: Double?
    let playedPercentage: Double?
    let played: Bool?
    let indexNumber: Int?
    let parentIndexNumber: Int?

    enum CodingKeys: String, CodingKey {
        case id, title, name, type, overview, genres, posterUrl, backdropUrl, seriesName, runtimeSeconds, playedPercentage
        case resumeSeconds = "resumePositionSeconds"
        case played, indexNumber, parentIndexNumber
    }

    var kind: String? { type }
    var displayTitle: String { type == "Episode" ? (seriesName ?? title ?? name ?? "Vault") : (title ?? name ?? "Vault") }
    var heroURL: URL? { [backdropUrl, posterUrl].compactMap { $0 }.compactMap(URL.init(string:)).first }
    var resumePositionSeconds: Double { resumeSeconds ?? 0 }
    var durationSeconds: Double? { runtimeSeconds }
    var isPlayable: Bool { kind == "Movie" || kind == "Episode" }
    var isPlayed: Bool { played ?? playedPercentage.map { $0 >= 90 } ?? false }

    static func isLaterEpisode(_ lhs: TopShelfLibraryItem, than rhs: TopShelfLibraryItem) -> Bool {
        let lhsSeason = lhs.parentIndexNumber ?? 0
        let rhsSeason = rhs.parentIndexNumber ?? 0
        if lhsSeason != rhsSeason { return lhsSeason > rhsSeason }
        return (lhs.indexNumber ?? 0) > (rhs.indexNumber ?? 0)
    }

    var playbackProgress: Double? {
        if let playedPercentage { return min(max(playedPercentage / 100, 0), 1) }
        guard let runtimeSeconds, runtimeSeconds > 0, resumePositionSeconds > 0 else { return nil }
        return min(max(resumePositionSeconds / runtimeSeconds, 0), 1)
    }
}
