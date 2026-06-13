import Foundation

enum StreamURLBuilder {
    /// Direct-stream URL handed to the FFmpeg demuxer:
    /// `GET {base}/Videos/{id}/stream?static=true`.
    /// Deliberately token-free: auth is sent as an `X-Emby-Token` HTTP header
    /// via libavformat's `headers` option (see Demuxer.open), so the token
    /// never shows up in server access logs, proxies or crash reports.
    static func directStream(baseURL: URL, itemId: String, mediaSourceId: String? = nil) -> URL? {
        guard var components = URLComponents(
            url: baseURL.appendingPathComponent("Videos/\(itemId)/stream"),
            resolvingAgainstBaseURL: false
        ) else { return nil }
        var query = [URLQueryItem(name: "static", value: "true")]
        if let mediaSourceId {
            query.append(URLQueryItem(name: "mediaSourceId", value: mediaSourceId))
        }
        components.queryItems = query
        return components.url
    }
}
