import Foundation

actor VaultClient {
    struct Configuration: Sendable {
        let baseURL: URL
        let token: String
        let userId: String
        let deviceId: String
    }

    nonisolated let config: Configuration
    private let session: URLSession
    private let decoder = JSONDecoder()
    private let encoder = JSONEncoder()

    init(config: Configuration) {
        self.config = config
        let sessionConfig = URLSessionConfiguration.default
        sessionConfig.timeoutIntervalForRequest = 15
        self.session = URLSession(configuration: sessionConfig)
    }

    func get<T: Decodable & Sendable>(_ path: String, query: [URLQueryItem] = []) async throws -> T {
        let (data, _) = try await perform(request(path: path, query: query, method: "GET", body: nil))
        do {
            return try decoder.decode(T.self, from: data)
        } catch {
            throw JellyfinError.decoding("\(path): \(error)")
        }
    }

    func post<Body: Encodable>(_ path: String, body: Body, query: [URLQueryItem] = []) async throws {
        let encoded = try encoder.encode(body)
        _ = try await perform(request(path: path, query: query, method: "POST", body: encoded))
    }

    // MARK: - Internals

    private func request(path: String, query: [URLQueryItem], method: String, body: Data?) throws -> URLRequest {
        let cleanPath = path.hasPrefix("/") ? String(path.dropFirst()) : path
        let url = config.baseURL.appendingPathComponent(cleanPath)
        guard var components = URLComponents(url: url, resolvingAgainstBaseURL: false) else {
            throw JellyfinError.invalidURL
        }
        if !query.isEmpty {
            components.queryItems = query
        }
        guard let finalURL = components.url else { throw JellyfinError.invalidURL }

        var request = URLRequest(url: finalURL)
        request.httpMethod = method
        request.setValue(
            "Bearer \(config.token)",
            forHTTPHeaderField: "Authorization"
        )
        if let body {
            request.httpBody = body
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }
        return request
    }

    private func perform(_ request: URLRequest) async throws -> (Data, HTTPURLResponse) {
        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: request)
        } catch {
            throw JellyfinError.transport(error.localizedDescription)
        }
        guard let http = response as? HTTPURLResponse else {
            throw JellyfinError.transport("Keine HTTP-Antwort")
        }
        switch http.statusCode {
        case 200..<300: return (data, http)
        case 401: throw JellyfinError.unauthorized
        case 404: throw JellyfinError.notFound
        default: throw JellyfinError.server(http.statusCode)
        }
    }
}
