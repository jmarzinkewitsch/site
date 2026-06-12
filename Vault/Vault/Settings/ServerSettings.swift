import Foundation
import Observation

/// UserDefaults-backed connection settings. Full settings UX comes later;
/// this is just enough to make milestones 1–3 usable.
@Observable
final class ServerSettings {
    private static let defaults = UserDefaults.standard

    var serverURLString: String {
        didSet { Self.defaults.set(serverURLString, forKey: "vault.serverURL") }
    }
    var token: String? {
        didSet { Self.defaults.set(token, forKey: "vault.token") }
    }
    var userId: String? {
        didSet { Self.defaults.set(userId, forKey: "vault.userId") }
    }
    var username: String {
        didSet { Self.defaults.set(username, forKey: "vault.username") }
    }
    /// Stable per-install device identifier sent in the auth header.
    let deviceId: String

    init() {
        serverURLString = Self.defaults.string(forKey: "vault.serverURL") ?? ""
        token = Self.defaults.string(forKey: "vault.token")
        userId = Self.defaults.string(forKey: "vault.userId")
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

    var isConfigured: Bool {
        serverURL != nil && !(token ?? "").isEmpty && !(userId ?? "").isEmpty
    }

    func clearCredentials() {
        token = nil
        userId = nil
    }
}
