import Foundation

enum JellyfinError: Error, LocalizedError {
    case invalidURL
    case unauthorized
    case notFound
    case server(Int)
    case decoding(String)
    case transport(String)

    var errorDescription: String? {
        switch self {
        case .invalidURL: return "Ungültige Server-URL"
        case .unauthorized: return "Nicht angemeldet oder Token ungültig"
        case .notFound: return "Nicht gefunden (404)"
        case .server(let code): return "Serverfehler (\(code))"
        case .decoding(let detail): return "Antwort nicht lesbar: \(detail)"
        case .transport(let detail): return "Verbindungsfehler: \(detail)"
        }
    }
}
