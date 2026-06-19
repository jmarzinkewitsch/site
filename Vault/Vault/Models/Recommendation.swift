import Foundation

/// Decodes vault-api's `/recommend` response. snake_case → camelCase is handled
/// by the client's `.convertFromSnakeCase` decoder.
struct RecommendationResponse: Decodable, Sendable {
    let shelves: [RecommendationShelf]
    let llmUsed: Bool

    enum CodingKeys: String, CodingKey {
        case shelves, llmUsed
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        shelves = try c.decodeIfPresent([RecommendationShelf].self, forKey: .shelves) ?? []
        llmUsed = try c.decodeIfPresent(Bool.self, forKey: .llmUsed) ?? false
    }
}

struct RecommendationShelf: Decodable, Identifiable, Sendable {
    let id: String
    let title: String
    let profile: String
    let items: [RecommendationItem]

    enum CodingKeys: String, CodingKey {
        case id, title, profile, items
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        title = try c.decodeIfPresent(String.self, forKey: .title) ?? "Empfehlungen"
        profile = try c.decodeIfPresent(String.self, forKey: .profile) ?? "both"
        id = try c.decodeIfPresent(String.self, forKey: .id) ?? "\(profile)-\(title)"
        items = try c.decodeIfPresent([RecommendationItem].self, forKey: .items) ?? []
    }
}

struct RecommendationItem: Decodable, Identifiable, Hashable, Sendable {
    let id: String
    let title: String
    let type: String          // "Movie" | "Series"
    let year: Int?
    let overview: String?
    let posterUrl: String?
    let backdropUrl: String?
    let score: Double
    let reason: String
    let status: String        // "playable" | "requestable"
    let libraryId: String?
    let tmdbId: Int?
    let communityRating: Double?  // 0–10 (≈ IMDB / TMDB vote)
    let criticRating: Double?     // 0–100 (≈ RT %)
    let matchScore: Int?
    let jannoScore: Int?
    let tannoScore: Int?
    let fearFactor: Int?
    let profile: String?
    let categoryTags: [String]

    enum CodingKeys: String, CodingKey {
        case id, title, type, year, overview, posterUrl, backdropUrl, score, reason, status, libraryId, tmdbId
        case communityRating, criticRating, matchScore, jannoScore, tannoScore, fearFactor, profile, categoryTags
    }

    init(
        id: String,
        title: String,
        type: String,
        year: Int?,
        overview: String?,
        posterUrl: String?,
        backdropUrl: String?,
        score: Double,
        reason: String,
        status: String,
        libraryId: String?,
        tmdbId: Int?,
        communityRating: Double?,
        criticRating: Double?,
        matchScore: Int?,
        jannoScore: Int?,
        tannoScore: Int?,
        fearFactor: Int?,
        profile: String?,
        categoryTags: [String]
    ) {
        self.id = id
        self.title = title
        self.type = type
        self.year = year
        self.overview = overview
        self.posterUrl = posterUrl
        self.backdropUrl = backdropUrl
        self.score = score
        self.reason = reason
        self.status = status
        self.libraryId = libraryId
        self.tmdbId = tmdbId
        self.communityRating = communityRating
        self.criticRating = criticRating
        self.matchScore = matchScore
        self.jannoScore = jannoScore
        self.tannoScore = tannoScore
        self.fearFactor = fearFactor
        self.profile = profile
        self.categoryTags = categoryTags
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        title = try c.decodeIfPresent(String.self, forKey: .title) ?? "Unbekannter Titel"
        type = try c.decodeIfPresent(String.self, forKey: .type) ?? "Movie"
        year = try c.decodeIfPresent(Int.self, forKey: .year)
        overview = try c.decodeIfPresent(String.self, forKey: .overview)
        posterUrl = try c.decodeIfPresent(String.self, forKey: .posterUrl)
        backdropUrl = try c.decodeIfPresent(String.self, forKey: .backdropUrl)
        score = try c.decodeIfPresent(Double.self, forKey: .score) ?? 0
        reason = try c.decodeIfPresent(String.self, forKey: .reason) ?? ""
        libraryId = try c.decodeIfPresent(String.self, forKey: .libraryId)
        tmdbId = try c.decodeIfPresent(Int.self, forKey: .tmdbId)
        let decodedStatus = try c.decodeIfPresent(String.self, forKey: .status)
        status = decodedStatus ?? (libraryId == nil ? "requestable" : "playable")
        communityRating = try c.decodeIfPresent(Double.self, forKey: .communityRating)
        criticRating = try c.decodeIfPresent(Double.self, forKey: .criticRating)
        matchScore = try c.decodeIfPresent(Int.self, forKey: .matchScore)
        jannoScore = try c.decodeIfPresent(Int.self, forKey: .jannoScore)
        tannoScore = try c.decodeIfPresent(Int.self, forKey: .tannoScore)
        fearFactor = try c.decodeIfPresent(Int.self, forKey: .fearFactor)
        profile = try c.decodeIfPresent(String.self, forKey: .profile)
        categoryTags = try c.decodeIfPresent([String].self, forKey: .categoryTags) ?? []
        if let decodedId = try c.decodeIfPresent(String.self, forKey: .id) {
            id = decodedId
        } else if let libraryId {
            id = libraryId
        } else if let tmdbId {
            id = "\(type)-\(tmdbId)"
        } else {
            id = "\(type)-\(title)"
        }
    }

    var isPlayable: Bool { status.lowercased() == "playable" }
    var isRequestable: Bool { status.lowercased() == "requestable" }

    static func == (lhs: RecommendationItem, rhs: RecommendationItem) -> Bool { lhs.id == rhs.id }
    func hash(into hasher: inout Hasher) { hasher.combine(id) }
}

/// Result of a POST /request/{movie,series}.
struct RequestResult: Decodable, Sendable {
    let ok: Bool
    let status: String        // "added" | "already_exists"
    let title: String
    let detail: String?
}

/// One item from GET /request/queue.
struct QueueItem: Decodable, Identifiable, Hashable, Sendable {
    let title: String
    let type: String          // "Movie" | "Series"
    let progress: Double      // 0...1
    let status: String?
    let timeLeft: String?

    var id: String { "\(type):\(title)" }
}
