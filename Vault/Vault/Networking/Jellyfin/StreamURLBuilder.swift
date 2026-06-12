import Foundation

enum StreamURLBuilder {
    /// Direct-stream URL handed straight to the FFmpeg demuxer:
    /// `GET {base}/Videos/{id}/stream?static=true&api_key={token}`.
    /// Auth goes via query parameter because libavformat sends no custom headers here.
    static func directStream(baseURL: URL, itemId: String, token: String, mediaSourceId: String? = nil) -> URL? {
        guard var components = URLComponents(
            url: baseURL.appendingPathComponent("Videos/\(itemId)/stream"),
            resolvingAgainstBaseURL: false
        ) else { return nil }
        var query = [
            URLQueryItem(name: "static", value: "true"),
            URLQueryItem(name: "api_key", value: token),
        ]
        if let mediaSourceId {
            query.append(URLQueryItem(name: "mediaSourceId", value: mediaSourceId))
        }
        components.queryItems = query
        return components.url
    }
}
