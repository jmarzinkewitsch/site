import Foundation

// MARK: - PickItem

/// One result from the picker endpoint.
struct PickItem: Decodable, Identifiable, Hashable, Sendable {
    let id: String
    let title: String
    let type: String          // "Movie" | "Series"
    let year: Int?
    let overview: String?
    let posterUrl: String?
    let backdropUrl: String?
    let logoUrl: String?
    let source: String        // "library" | "discover"
    let status: String        // "playable" | "requestable"
    let libraryId: String?
    let tmdbId: Int?
    let reason: String
    let fearFactor: Int?
    let communityRating: Double?

    // convertFromSnakeCase handles poster_url → posterUrl, etc.
    // logoUrl and tmdbId map fine. No explicit CodingKeys needed.

    var isPlayable: Bool { status.lowercased() == "playable" }
    var isRequestable: Bool { status.lowercased() == "requestable" }

    /// Bridge to the existing request/detail flow.
    var asRecommendationItem: RecommendationItem {
        RecommendationItem(
            id: id,
            title: title,
            type: type,
            year: year,
            overview: overview,
            posterUrl: posterUrl,
            backdropUrl: backdropUrl,
            score: 0,
            reason: reason,
            status: status,
            libraryId: libraryId,
            tmdbId: tmdbId,
            communityRating: communityRating,
            criticRating: nil,
            matchScore: nil,
            jannoScore: nil,
            tannoScore: nil,
            fearFactor: fearFactor,
            profile: nil,
            categoryTags: []
        )
    }

    static func == (lhs: PickItem, rhs: PickItem) -> Bool { lhs.id == rhs.id }
    func hash(into hasher: inout Hasher) { hasher.combine(id) }
}

// MARK: - PickerResponse

struct PickerResponse: Decodable, Sendable {
    let libraryPick: PickItem?
    let discoverPick: PickItem?
    let alternatives: [PickItem]
    let llmUsed: Bool

    enum CodingKeys: String, CodingKey {
        case libraryPick, discoverPick, alternatives, llmUsed
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        libraryPick = try c.decodeIfPresent(PickItem.self, forKey: .libraryPick)
        discoverPick = try c.decodeIfPresent(PickItem.self, forKey: .discoverPick)
        alternatives = try c.decodeIfPresent([PickItem].self, forKey: .alternatives) ?? []
        llmUsed = try c.decodeIfPresent(Bool.self, forKey: .llmUsed) ?? false
    }
}

// MARK: - PickerRequest

/// POST body for `recommend/picker`. Explicit CodingKeys because the client's
/// `.convertToSnakeCase` encoder would otherwise mangle camelCase incorrectly
/// for the two multi-word keys (moodFear → mood_fear, excludeIds → exclude_ids).
struct PickerRequest: Encodable, Hashable {
    let profile: String           // "janno" | "tanno" | "both"
    let genres: [String]
    let moodFear: Int?
    let length: String?           // "short" | "feature" | "series" | nil
    let surprise: Bool
    let excludeIds: [String]

    enum CodingKeys: String, CodingKey {
        case profile, genres, length, surprise
        case moodFear   = "mood_fear"
        case excludeIds = "exclude_ids"
    }
}

// MARK: - PersonaProfile

struct PersonaProfile: Codable, Identifiable, Sendable {
    let person: String
    var favoriteGenres: [String]
    var fearComfort: Int

    var id: String { person }

    enum CodingKeys: String, CodingKey {
        case person
        case favoriteGenres = "favorite_genres"
        case fearComfort    = "fear_comfort"
    }
}

// MARK: - PickerLength

enum PickerLength: String, CaseIterable, Hashable {
    case short   = "short"
    case feature = "feature"
    case series  = "series"

    var label: String {
        switch self {
        case .short:   return "Kurz · <90 Min"
        case .feature: return "Abendfüllend"
        case .series:  return "Serie"
        }
    }
}

// MARK: - Genre chips

/// Curated genre labels aligned with the backend's GENRE_NAME_TO_TMDB_ID mapping.
let pickerGenreChips: [String] = [
    "Action",
    "Thriller",
    "Horror",
    "Komödie",
    "Drama",
    "Sci-Fi",
    "Romantik",
    "Animation",
    "Krimi",
    "Dokumentation",
    "Fantasy",
    "Abenteuer",
]
