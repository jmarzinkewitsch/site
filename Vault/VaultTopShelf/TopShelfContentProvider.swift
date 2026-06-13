import Foundation
import TVServices

final class TopShelfContentProvider: TVTopShelfContentProvider {
    private let client = TopShelfVaultClient()

    override func loadTopShelfContent(completionHandler: @escaping (TVTopShelfContent?) -> Void) {
        Task {
            let content = try? await client.loadContent()
            completionHandler(content)
        }
    }
}

private actor TopShelfVaultClient {
    private static let appGroupIdentifier = "group.de.marzinkewitsch.vault"
    private static let maxItems = 10

    private let decoder: JSONDecoder
    private let session: URLSession

    init() {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        self.decoder = decoder

        let configuration = URLSessionConfiguration.ephemeral
        configuration.timeoutIntervalForRequest = 3
        configuration.timeoutIntervalForResource = 3
        self.session = URLSession(configuration: configuration)
    }

    func loadContent() async throws -> TVTopShelfContent? {
        guard let defaults = UserDefaults(suiteName: Self.appGroupIdentifier),
              let rawURL = defaults.string(forKey: "vault.serverURL"),
              let baseURL = normalizedBaseURL(from: rawURL),
              let token = defaults.string(forKey: "vault.token"),
              !token.isEmpty
        else { return nil }

        async let continueItems: [TopShelfItem] = get("library/continue", baseURL: baseURL, token: token)
        async let latestMovies: [TopShelfItem] = get("library/latest", baseURL: baseURL, token: token, query: [URLQueryItem(name: "type", value: "Movie")])
        async let latestSeries: [TopShelfItem] = get("library/latest", baseURL: baseURL, token: token, query: [URLQueryItem(name: "type", value: "Series")])

        var seen = Set<String>()
        let curated = try await (continueItems.map { ($0, true) } + (latestMovies + latestSeries).map { ($0, false) })
            .filter { item, _ in
                guard seen.insert(item.id).inserted else { return false }
                return item.heroURL != nil
            }
            .prefix(Self.maxItems)
            .compactMap(makeCarouselItem)

        guard !curated.isEmpty else { return nil }
        return TVTopShelfCarouselContent(style: .details, items: Array(curated))
    }

    private func get<T: Decodable>(_ path: String, baseURL: URL, token: String, query: [URLQueryItem] = []) async throws -> T {
        let url = baseURL.appendingPathComponent(path)
        guard var components = URLComponents(url: url, resolvingAgainstBaseURL: false) else { throw URLError(.badURL) }
        if !query.isEmpty { components.queryItems = query }
        guard let finalURL = components.url else { throw URLError(.badURL) }

        var request = URLRequest(url: finalURL)
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Accept")

        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse, 200..<300 ~= http.statusCode else {
            throw URLError(.badServerResponse)
        }
        return try decoder.decode(T.self, from: data)
    }

    private func normalizedBaseURL(from rawURL: String) -> URL? {
        var trimmed = rawURL.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return nil }
        if !trimmed.contains("://") { trimmed = "http://" + trimmed }
        while trimmed.hasSuffix("/") { trimmed.removeLast() }
        return URL(string: trimmed)
    }

    private func makeCarouselItem(item: TopShelfItem, isContinueItem: Bool) -> TVTopShelfCarouselItem? {
        guard let heroURL = item.heroURL else { return nil }

        let carouselItem = TVTopShelfCarouselItem(identifier: item.id)
        carouselItem.title = item.displayTitle
        carouselItem.summary = item.overview
        carouselItem.genre = item.genres?.joined(separator: ", ")
        if let duration = item.durationSeconds {
            carouselItem.duration = duration
        }
        if isContinueItem, let duration = item.durationSeconds, duration > 0 {
            carouselItem.playbackProgress = item.resumePositionSeconds / duration
        }
        carouselItem.setImageURL(heroURL, for: .screenScale1x)
        carouselItem.setImageURL(heroURL, for: .screenScale2x)
        carouselItem.imageShape = .hdtv
        carouselItem.displayAction = TVTopShelfAction(url: URL(string: "vault://item/\(item.id)")!)
        carouselItem.playAction = TVTopShelfAction(url: URL(string: "vault://play/\(item.id)")!)
        return carouselItem
    }
}

private struct TopShelfItem: Decodable {
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
    let runTimeTicks: Int64?
    let userData: UserData?

    var displayTitle: String? {
        if type == "Episode", let seriesName { return seriesName }
        return title ?? name
    }

    var heroURL: URL? {
        (backdropUrl ?? posterUrl).flatMap(URL.init(string:))
    }

    var durationSeconds: TimeInterval? {
        runtimeSeconds ?? runTimeTicks.map { TimeInterval($0) / 10_000_000 }
    }

    var resumePositionSeconds: TimeInterval {
        resumeSeconds ?? userData.map { TimeInterval($0.playbackPositionTicks ?? 0) / 10_000_000 } ?? 0
    }

    enum CodingKeys: String, CodingKey {
        case id, title, name, type, overview, genres, posterUrl, backdropUrl, seriesName, runtimeSeconds
        case resumeSeconds = "resumePositionSeconds"
        case runTimeTicks = "RunTimeTicks"
        case userData = "UserData"
    }
}

private struct UserData: Decodable {
    let playbackPositionTicks: Int64?
}
