import Foundation

struct BaseItemDto: Decodable, Identifiable, Hashable, Sendable {
    let id: String
    let name: String?
    let type: String?
    let overview: String?
    let runTimeTicks: Int64?
    let productionYear: Int?
    let genres: [String]?
    let communityRating: Double?
    let officialRating: String?
    let imageTags: [String: String]?
    let backdropImageTags: [String]?
    let seriesId: String?
    let seriesName: String?
    let seasonId: String?
    let seasonName: String?
    let indexNumber: Int?
    let parentIndexNumber: Int?
    let userData: UserItemDataDto?
    let mediaSources: [MediaSourceInfo]?
    let mediaStreams: [MediaStream]?

    enum CodingKeys: String, CodingKey {
        case id = "Id"
        case name = "Name"
        case type = "Type"
        case overview = "Overview"
        case runTimeTicks = "RunTimeTicks"
        case productionYear = "ProductionYear"
        case genres = "Genres"
        case communityRating = "CommunityRating"
        case officialRating = "OfficialRating"
        case imageTags = "ImageTags"
        case backdropImageTags = "BackdropImageTags"
        case seriesId = "SeriesId"
        case seriesName = "SeriesName"
        case seasonId = "SeasonId"
        case seasonName = "SeasonName"
        case indexNumber = "IndexNumber"
        case parentIndexNumber = "ParentIndexNumber"
        case userData = "UserData"
        case mediaSources = "MediaSources"
        case mediaStreams = "MediaStreams"
    }

    var kind: ItemKind? { type.flatMap(ItemKind.init(rawValue:)) }

    /// "S2 E5" for episodes, nil otherwise.
    var episodeCode: String? {
        guard kind == .episode else { return nil }
        let s = parentIndexNumber.map { "S\($0)" } ?? ""
        let e = indexNumber.map { "E\($0)" } ?? ""
        let code = [s, e].filter { !$0.isEmpty }.joined(separator: " ")
        return code.isEmpty ? nil : code
    }

    var allMediaStreams: [MediaStream] {
        mediaStreams ?? mediaSources?.first?.mediaStreams ?? []
    }

    var resumePositionSeconds: Double {
        Double(userData?.playbackPositionTicks ?? 0) / 10_000_000
    }

    var durationSeconds: Double? {
        let ticks = runTimeTicks ?? mediaSources?.first?.runTimeTicks
        return ticks.map { Double($0) / 10_000_000 }
    }

    static func == (lhs: BaseItemDto, rhs: BaseItemDto) -> Bool { lhs.id == rhs.id }
    func hash(into hasher: inout Hasher) { hasher.combine(id) }
}
