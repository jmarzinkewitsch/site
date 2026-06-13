import Foundation

struct QueryResult<T: Decodable & Sendable>: Decodable, Sendable {
    let items: [T]
    let totalRecordCount: Int?

    enum CodingKeys: String, CodingKey {
        case items = "Items"
        case totalRecordCount = "TotalRecordCount"
    }
}
