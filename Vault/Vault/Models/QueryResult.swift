import Foundation

struct QueryResult<T: Decodable & Sendable>: Decodable, Sendable {
    let items: [T]
    let totalRecordCount: Int?

    init(items: [T], totalRecordCount: Int?) {
        self.items = items
        self.totalRecordCount = totalRecordCount
    }

    enum CodingKeys: String, CodingKey {
        case items = "Items"
        case totalRecordCount = "TotalRecordCount"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        items = try container.decode([T].self, forKey: .items)
        totalRecordCount = try container.decodeIfPresent(Int.self, forKey: .totalRecordCount)
    }
}
