import Foundation

enum JellyfinAuthHeader {
    static let clientName = "Vault"
    static let deviceName = "Apple TV"
    static let version = "0.1.0"

    /// `Authorization: MediaBrowser Client="Vault", Device="Apple TV", DeviceId="…", Version="0.1.0", Token="…"`
    /// Token is omitted on the initial authentication call.
    static func value(token: String?, deviceId: String) -> String {
        var value = "MediaBrowser Client=\"\(clientName)\", Device=\"\(deviceName)\", "
            + "DeviceId=\"\(deviceId)\", Version=\"\(version)\""
        if let token, !token.isEmpty {
            value += ", Token=\"\(token)\""
        }
        return value
    }
}
