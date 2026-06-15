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
            return merged.compactMap(makeCarouselItem).prefix(10).map { $0 }
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

    private func curated(continueItems: [TopShelfLibraryItem], latestItems: [TopShelfLibraryItem]) -> [TopShelfLibraryItem] {
        var seen = Set<String>()
        return (continueItems + latestItems).filter { item in
            guard !seen.contains(item.id) else { return false }
            seen.insert(item.id)
            return item.heroURL != nil
        }
    }

    private func makeCarouselItem(from item: TopShelfLibraryItem) -> TVTopShelfCarouselItem? {
        guard let imageURL = item.heroURL else { return nil }
        let carouselItem = TVTopShelfCarouselItem(identifier: item.id)
        carouselItem.title = item.displayTitle
        carouselItem.summary = item.overview
        carouselItem.genre = item.genres?.prefix(3).joined(separator: " · ")
        if let duration = item.durationSeconds {
            carouselItem.duration = duration
        }
        if let progress = item.playbackProgress {
            carouselItem.playbackProgress = progress
        }
        carouselItem.setImageURL(imageURL, for: .screenScale1x)
        carouselItem.displayAction = TVTopShelfAction(url: URL(string: "vault://item/\(item.id)")!)
        if item.isPlayable {
            carouselItem.playAction = TVTopShelfAction(url: URL(string: "vault://play/\(item.id)")!)
        }
        return carouselItem
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
