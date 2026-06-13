import Foundation

/// vault-api library item. The tvOS app no longer decodes Jellyfin DTOs directly.
struct BaseItemDto: Decodable, Identifiable, Hashable, Sendable {
    let id: String
    let type: String
    let title: String
    let overview: String?
    let year: Int?
    let genres: [String]?
    let runtimeSeconds: Double?
    let communityRating: Double?
    let criticRating: Double?
    let userRating: Double?
    let officialRating: String?
    let posterURL: URL?
    let backdropURL: URL?
    let played: Bool
    let playedPercentage: Double?
    let resumePositionSeconds: Double
    let seriesId: String?
    let seriesName: String?
    let seasonId: String?
    let indexNumber: Int?
    let parentIndexNumber: Int?
    let episodeCode: String?

    enum CodingKeys: String, CodingKey {
        case id, type, title, overview, year, genres, played
        case runtimeSeconds = "runtime_seconds"
        case communityRating = "community_rating"
        case criticRating = "critic_rating"
        case userRating = "user_rating"
        case officialRating = "official_rating"
        case posterURL = "poster_url"
        case backdropURL = "backdrop_url"
        case playedPercentage = "played_percentage"
        case resumePositionSeconds = "resume_position_seconds"
        case seriesId = "series_id"
        case seriesName = "series_name"
        case seasonId = "season_id"
        case indexNumber = "index_number"
        case parentIndexNumber = "parent_index_number"
        case episodeCode = "episode_code"
    }

    var name: String? { title }
    var productionYear: Int? { year }
    var kind: ItemKind? { ItemKind(rawValue: type) }
    var durationSeconds: Double? { runtimeSeconds }
    var allMediaStreams: [MediaStream] { [] }
    var mediaSources: [MediaSourceInfo]? { nil }

    static func == (lhs: BaseItemDto, rhs: BaseItemDto) -> Bool { lhs.id == rhs.id }
    func hash(into hasher: inout Hasher) { hasher.combine(id) }
}
