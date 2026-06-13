import Foundation
import Observation

/// UserDefaults-backed vault-api connection settings. The app knows only the
/// vault-api URL and its bearer token; all Jellyfin/arr/TMDB credentials live
/// in the backend admin UI.
@Observable
final class ServerSettings {
    private static let defaults = UserDefaults.standard

    var serverURLString: String {
        didSet { Self.defaults.set(serverURLString, forKey: "vault.serverURL") }
    }
    var token: String? {
        didSet { Self.defaults.set(token, forKey: "vault.token") }
    }
    var username: String {
        didSet { Self.defaults.set(username, forKey: "vault.username") }
    }
    let deviceId: String

    init() {
        serverURLString = Self.defaults.string(forKey: "vault.serverURL") ?? ""
        token = Self.defaults.string(forKey: "vault.token")
        username = Self.defaults.string(forKey: "vault.username") ?? ""
        if let existing = Self.defaults.string(forKey: "vault.deviceId") {
            deviceId = existing
        } else {
            let fresh = UUID().uuidString
            Self.defaults.set(fresh, forKey: "vault.deviceId")
            deviceId = fresh
        }
    }

    var serverURL: URL? {
        var trimmed = serverURLString.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return nil }
        if !trimmed.contains("://") { trimmed = "http://" + trimmed }
        while trimmed.hasSuffix("/") { trimmed.removeLast() }
        return URL(string: trimmed)
    }

    var isConfigured: Bool { serverURL != nil && !(token ?? "").isEmpty }

    func clearCredentials() { token = nil }
}
