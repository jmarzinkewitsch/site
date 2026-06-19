import Foundation

struct VaultLibraryService: Sendable {
    let client: VaultClient

    func resumeItems(limit: Int = 12) async throws -> [BaseItemDto] {
        let items: [BaseItemDto] = try await client.get("library/continue")
        return Array(items.prefix(limit))
    }

    func nextUp(limit: Int = 12) async throws -> [BaseItemDto] {
        let items: [BaseItemDto] = try await client.get("library/nextup", query: [
            URLQueryItem(name: "limit", value: "\(limit)")
        ])
        return Array(items.prefix(limit))
    }

    /// Recently added shelf — hits the date-added "latest" endpoint, not the
    /// SortName-ordered list, so newly added titles actually show up.
    func latest(kind: ItemKind, limit: Int = 16) async throws -> [BaseItemDto] {
        try await client.get("library/latest", query: [
            URLQueryItem(name: "type", value: kind.rawValue),
            URLQueryItem(name: "limit", value: "\(limit)")
        ])
    }

    func shelf(sort: String, genres: [String] = [], unplayed: Bool = false, type: ItemKind = .movie, limit: Int = 16) async throws -> [BaseItemDto] {
        var query = [
            URLQueryItem(name: "sort", value: sort),
            URLQueryItem(name: "type", value: type.rawValue),
            URLQueryItem(name: "limit", value: "\(limit)"),
        ]
        if !genres.isEmpty { query.append(URLQueryItem(name: "genres", value: genres.joined(separator: ","))) }
        if unplayed { query.append(URLQueryItem(name: "unplayed", value: "true")) }
        return try await client.get("library/shelf", query: query)
    }

    func items(kind: ItemKind, startIndex: Int, limit: Int = 100) async throws -> QueryResult<BaseItemDto> {
        let path = kind == .series ? "library/series" : "library/movies"
        let items: [BaseItemDto] = try await client.get(path, query: [
            URLQueryItem(name: "start", value: "\(startIndex)"),
            URLQueryItem(name: "limit", value: "\(limit)")
        ])
        let total = items.count < limit ? startIndex + items.count : startIndex + items.count + 1
        return QueryResult(items: items, totalRecordCount: total)
    }

    func item(id: String) async throws -> BaseItemDto {
        try await client.get("library/item/\(id)")
    }

    func nextEpisode(after itemId: String) async throws -> BaseItemDto? {
        try await client.get("library/item/\(itemId)/next-episode")
    }

    func trailerStream(itemId: String) async throws -> TrailerStream {
        try await client.get("library/item/\(itemId)/trailer-stream")
    }

    func setRating(itemId: String, rating: Double) async throws {
        try await client.post("library/item/\(itemId)/rating", body: VaultRatingUpdate(rating: rating))
    }

    func setWatched(itemId: String, watched: Bool) async throws {
        try await client.post("library/item/\(itemId)/watched", body: VaultWatchedUpdate(watched: watched))
    }

    func saveRatingSnapshot(itemId: String, snapshot: VaultRatingSnapshot) async throws {
        try await client.post("ratings/item/\(itemId)/snapshot", body: snapshot)
    }

    func seasons(seriesId: String) async throws -> [BaseItemDto] {
        try await client.get("library/series/\(seriesId)/seasons")
    }

    func episodes(seriesId: String, seasonId: String) async throws -> [BaseItemDto] {
        try await client.get("library/series/\(seriesId)/seasons/\(seasonId)/episodes")
    }

    func searchSubtitles(itemId: String, languages: [String]) async throws -> [RemoteSubtitleInfo] {
        let lang = languages.joined(separator: ",")
        return try await client.get(
            "library/item/\(itemId)/subtitles/search",
            query: [URLQueryItem(name: "languages", value: lang)]
        )
    }

    func downloadSubtitle(itemId: String, subtitleId: String) async throws -> [SubtitleTrackInfo] {
        try await client.post(
            "library/item/\(itemId)/subtitles/download",
            body: SubtitleDownloadRequest(subtitleId: subtitleId)
        )
    }
}

struct AudioTrackInfo: Decodable, Hashable, Sendable {
    let index: Int
    let language: String?
    let codec: String?
    let channels: Int?
    let displayTitle: String?

    var label: String {
        if let displayTitle, !displayTitle.isEmpty { return displayTitle }
        let lang = language?.uppercased() ?? "Audio"
        let codecText = codec?.uppercased()
        let channelText = channels.map { $0 >= 6 ? "5.1" : "\($0).0" }
        return [lang, codecText, channelText].compactMap { $0 }.joined(separator: " · ")
    }
}

struct SubtitleTrackInfo: Decodable, Hashable, Sendable {
    let index: Int
    let language: String?
    let codec: String?
    let displayTitle: String?
    /// External subs aren't in the direct stream — the player downloads and
    /// parses them from `deliveryURL` instead of decoding a container stream.
    var isExternal: Bool = false
    var deliveryURL: URL?

    enum CodingKeys: String, CodingKey {
        case index, language, codec, displayTitle, isExternal
        case deliveryURL = "deliveryUrl"
    }

    init(index: Int, language: String?, codec: String?, displayTitle: String?,
         isExternal: Bool = false, deliveryURL: URL? = nil) {
        self.index = index
        self.language = language
        self.codec = codec
        self.displayTitle = displayTitle
        self.isExternal = isExternal
        self.deliveryURL = deliveryURL
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        index = try c.decode(Int.self, forKey: .index)
        language = try c.decodeIfPresent(String.self, forKey: .language)
        codec = try c.decodeIfPresent(String.self, forKey: .codec)
        displayTitle = try c.decodeIfPresent(String.self, forKey: .displayTitle)
        isExternal = try c.decodeIfPresent(Bool.self, forKey: .isExternal) ?? false
        deliveryURL = try c.decodeIfPresent(URL.self, forKey: .deliveryURL)
    }

    var label: String {
        if let displayTitle, !displayTitle.isEmpty { return displayTitle }
        let lang = language?.uppercased() ?? "Untertitel"
        let codecText = codec?.uppercased()
        return [lang, codecText].compactMap { $0 }.joined(separator: " · ")
    }
}

struct StreamSegment: Decodable, Hashable, Sendable {
    let type: String
    let start: Double
    let end: Double

    var title: String {
        type == "outro" ? "Abspann überspringen" : "Intro überspringen"
    }
}

struct TrailerStream: Decodable, Sendable {
    let url: String
    let container: String?
}

/// Trickplay (scrubbing thumbnail) metadata delivered by the server alongside
/// the stream. The template URL contains a literal `{index}` placeholder that
/// the client replaces with the tile-sheet index before fetching.
struct TrickplayInfo: Decodable, Hashable, Sendable {
    let interval: Int
    let tileWidth: Int
    let tileHeight: Int
    let thumbnailWidth: Int
    let thumbnailHeight: Int
    let thumbnailCount: Int
    /// URL template — contains the literal string `{index}` which the client
    /// replaces with the zero-based sheet index to build the real URL.
    let tileURLTemplate: String

    enum CodingKeys: String, CodingKey {
        case interval
        case tileWidth
        case tileHeight
        case thumbnailWidth
        case thumbnailHeight
        case thumbnailCount
        case tileURLTemplate = "tileUrlTemplate"
    }
}

struct StreamInfo: Decodable, Sendable {
    let url: String
    let container: String?
    let runtimeSeconds: Double?
    let audioTracks: [AudioTrackInfo]
    let subtitleTracks: [SubtitleTrackInfo]?
    let segments: [StreamSegment]?
    let trickplay: TrickplayInfo?
}

struct VaultProgressUpdate: Encodable {
    let positionSeconds: Double
    let isPaused: Bool
}

struct VaultRatingUpdate: Encodable {
    let rating: Double
}

struct VaultWatchedUpdate: Encodable {
    let watched: Bool
}

struct VaultRatingSnapshot: Encodable {
    let title: String
    let type: String
    let year: Int?
    let tmdbId: Int?
    let imdbId: String?
    let jannoRating: Double?
    let tannoRating: Double?
    let tannoFearFactor: Double?
}

// MARK: - Online subtitle search

struct RemoteSubtitleInfo: Decodable, Hashable, Sendable, Identifiable {
    let id: String
    let providerName: String?
    let name: String?
    let format: String?
    let language: String?
    let downloadCount: Int?
    let communityRating: Double?
    let isHashMatch: Bool?
    let comment: String?

    var label: String {
        var parts: [String] = []
        if let name, !name.isEmpty { parts.append(name) }
        if let lang = language?.uppercased() { parts.append(lang) }
        if let provider = providerName, !provider.isEmpty { parts.append("(\(provider))") }
        if let dl = downloadCount { parts.append("↓\(dl)") }
        return parts.isEmpty ? id : parts.joined(separator: " · ")
    }
}

private struct SubtitleDownloadRequest: Encodable {
    let subtitleId: String

    enum CodingKeys: String, CodingKey {
        case subtitleId = "subtitle_id"
    }
}
