import Foundation

struct MediaSourceInfo: Decodable, Sendable {
    let id: String?
    let container: String?
    let runTimeTicks: Int64?
    let mediaStreams: [MediaStream]?

    enum CodingKeys: String, CodingKey {
        case id = "Id"
        case container = "Container"
        case runTimeTicks = "RunTimeTicks"
        case mediaStreams = "MediaStreams"
    }
}

struct MediaStream: Decodable, Sendable {
    let codec: String?
    let type: String?
    let language: String?
    let displayTitle: String?
    let channels: Int?
    let width: Int?
    let height: Int?
    let videoRange: String?
    let index: Int?

    enum CodingKeys: String, CodingKey {
        case codec = "Codec"
        case type = "Type"
        case language = "Language"
        case displayTitle = "DisplayTitle"
        case channels = "Channels"
        case width = "Width"
        case height = "Height"
        case videoRange = "VideoRange"
        case index = "Index"
    }
}
