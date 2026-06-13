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
    let criticRating: Double?
    let officialRating: String?
    let posterUrl: String?
    let backdropUrl: String?
    let seriesId: String?
    let seriesName: String?
    let seasonId: String?
    let seasonName: String?
    let indexNumber: Int?
    let parentIndexNumber: Int?
    let episodeCodeValue: String?
    let userData: UserItemDataDto?
    let mediaSources: [MediaSourceInfo]?
    let mediaStreams: [MediaStream]?
    let runtimeSeconds: Double?
    let resumeSeconds: Double
    let playedPercentage: Double?

    enum CodingKeys: String, CodingKey {
        case id, type, overview, genres, criticRating, officialRating, posterUrl, backdropUrl
        case seriesId, seriesName, seasonId, seasonName, indexNumber, parentIndexNumber
        case runtimeSeconds, playedPercentage
        case title, year, communityRating, resumePositionSeconds, episodeCode
        case legacyId = "Id", name = "Name", legacyType = "Type", legacyOverview = "Overview"
        case runTimeTicks = "RunTimeTicks", productionYear = "ProductionYear", legacyGenres = "Genres"
        case legacyCommunityRating = "CommunityRating", legacyOfficialRating = "OfficialRating"
        case legacySeriesId = "SeriesId", legacySeriesName = "SeriesName", legacySeasonId = "SeasonId"
        case legacySeasonName = "SeasonName", legacyIndexNumber = "IndexNumber", legacyParentIndexNumber = "ParentIndexNumber"
        case userData = "UserData", mediaSources = "MediaSources", mediaStreams = "MediaStreams"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decodeIfPresent(String.self, forKey: .id) ?? c.decode(String.self, forKey: .legacyId)
        name = try c.decodeIfPresent(String.self, forKey: .title) ?? c.decodeIfPresent(String.self, forKey: .name)
        type = try c.decodeIfPresent(String.self, forKey: .type) ?? c.decodeIfPresent(String.self, forKey: .legacyType)
        overview = try c.decodeIfPresent(String.self, forKey: .overview) ?? c.decodeIfPresent(String.self, forKey: .legacyOverview)
        runTimeTicks = try c.decodeIfPresent(Int64.self, forKey: .runTimeTicks)
        runtimeSeconds = try c.decodeIfPresent(Double.self, forKey: .runtimeSeconds)
        productionYear = try c.decodeIfPresent(Int.self, forKey: .year) ?? c.decodeIfPresent(Int.self, forKey: .productionYear)
        genres = try c.decodeIfPresent([String].self, forKey: .genres) ?? c.decodeIfPresent([String].self, forKey: .legacyGenres)
        communityRating = try c.decodeIfPresent(Double.self, forKey: .communityRating) ?? c.decodeIfPresent(Double.self, forKey: .legacyCommunityRating)
        criticRating = try c.decodeIfPresent(Double.self, forKey: .criticRating)
        officialRating = try c.decodeIfPresent(String.self, forKey: .officialRating) ?? c.decodeIfPresent(String.self, forKey: .legacyOfficialRating)
        posterUrl = try c.decodeIfPresent(String.self, forKey: .posterUrl)
        backdropUrl = try c.decodeIfPresent(String.self, forKey: .backdropUrl)
        seriesId = try c.decodeIfPresent(String.self, forKey: .seriesId) ?? c.decodeIfPresent(String.self, forKey: .legacySeriesId)
        seriesName = try c.decodeIfPresent(String.self, forKey: .seriesName) ?? c.decodeIfPresent(String.self, forKey: .legacySeriesName)
        seasonId = try c.decodeIfPresent(String.self, forKey: .seasonId) ?? c.decodeIfPresent(String.self, forKey: .legacySeasonId)
        seasonName = try c.decodeIfPresent(String.self, forKey: .seasonName) ?? c.decodeIfPresent(String.self, forKey: .legacySeasonName)
        indexNumber = try c.decodeIfPresent(Int.self, forKey: .indexNumber) ?? c.decodeIfPresent(Int.self, forKey: .legacyIndexNumber)
        parentIndexNumber = try c.decodeIfPresent(Int.self, forKey: .parentIndexNumber) ?? c.decodeIfPresent(Int.self, forKey: .legacyParentIndexNumber)
        episodeCodeValue = try c.decodeIfPresent(String.self, forKey: .episodeCode)
        userData = try c.decodeIfPresent(UserItemDataDto.self, forKey: .userData)
        mediaSources = try c.decodeIfPresent([MediaSourceInfo].self, forKey: .mediaSources)
        mediaStreams = try c.decodeIfPresent([MediaStream].self, forKey: .mediaStreams)
        resumeSeconds = try c.decodeIfPresent(Double.self, forKey: .resumePositionSeconds) ?? 0
        playedPercentage = try c.decodeIfPresent(Double.self, forKey: .playedPercentage)
    }

    var kind: ItemKind? { type.flatMap(ItemKind.init(rawValue:)) }
    var episodeCode: String? {
        if let episodeCodeValue { return episodeCodeValue }
        guard kind == .episode else { return nil }
        let s = parentIndexNumber.map { "S\($0)" } ?? ""
        let e = indexNumber.map { "E\($0)" } ?? ""
        let code = [s, e].filter { !$0.isEmpty }.joined(separator: " ")
        return code.isEmpty ? nil : code
    }
    var allMediaStreams: [MediaStream] { mediaStreams ?? mediaSources?.first?.mediaStreams ?? [] }
    var resumePositionSeconds: Double { resumeSeconds > 0 ? resumeSeconds : Double(userData?.playbackPositionTicks ?? 0) / 10_000_000 }
    var durationSeconds: Double? { runtimeSeconds ?? (runTimeTicks ?? mediaSources?.first?.runTimeTicks).map { Double($0) / 10_000_000 } }
    static func == (lhs: BaseItemDto, rhs: BaseItemDto) -> Bool { lhs.id == rhs.id }
    func hash(into hasher: inout Hasher) { hasher.combine(id) }
}
