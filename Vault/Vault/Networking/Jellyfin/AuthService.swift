import Foundation

/// Sign-in and token validation. Standalone (not the actor) because the
/// initial authentication call has no token yet.
struct AuthService: Sendable {
    private struct Credentials: Encodable {
        let Username: String
        let Pw: String
    }

    func authenticate(
        serverURL: URL, username: String, password: String, deviceId: String
    ) async throws -> AuthenticationResult {
        var request = URLRequest(url: serverURL.appendingPathComponent("Users/AuthenticateByName"))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue(
            JellyfinAuthHeader.value(token: nil, deviceId: deviceId),
            forHTTPHeaderField: "Authorization"
        )
        request.httpBody = try JSONEncoder().encode(Credentials(Username: username, Pw: password))
        request.timeoutInterval = 15

        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await URLSession.shared.data(for: request)
        } catch {
            throw JellyfinError.transport(error.localizedDescription)
        }
        guard let http = response as? HTTPURLResponse else {
            throw JellyfinError.transport("Keine HTTP-Antwort")
        }
        switch http.statusCode {
        case 200..<300:
            do {
                return try JSONDecoder().decode(AuthenticationResult.self, from: data)
            } catch {
                throw JellyfinError.decoding("AuthenticateByName: \(error)")
            }
        case 401: throw JellyfinError.unauthorized
        default: throw JellyfinError.server(http.statusCode)
        }
    }

    /// Validates an existing token and returns the user it belongs to.
    func validate(client: JellyfinClient) async throws -> UserDto {
        try await client.get("Users/Me")
    }
}
