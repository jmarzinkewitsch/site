import Foundation

enum ImageURLBuilder {
    static func primary(baseURL: URL, itemId: String, tag: String?, maxWidth: Int) -> URL? {
        build(baseURL: baseURL, path: "Items/\(itemId)/Images/Primary", tag: tag, maxWidth: maxWidth)
    }

    static func backdrop(baseURL: URL, itemId: String, tag: String?, maxWidth: Int) -> URL? {
        build(baseURL: baseURL, path: "Items/\(itemId)/Images/Backdrop/0", tag: tag, maxWidth: maxWidth)
    }

    private static func build(baseURL: URL, path: String, tag: String?, maxWidth: Int) -> URL? {
        guard var components = URLComponents(
            url: baseURL.appendingPathComponent(path), resolvingAgainstBaseURL: false
        ) else { return nil }
        var query = [
            URLQueryItem(name: "maxWidth", value: "\(maxWidth)"),
            URLQueryItem(name: "quality", value: "90"),
        ]
        if let tag {
            query.append(URLQueryItem(name: "tag", value: tag))
        }
        components.queryItems = query
        return components.url
    }
}
