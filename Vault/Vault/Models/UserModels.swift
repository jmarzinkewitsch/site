import Foundation

struct UserDto: Decodable, Sendable {
    let id: String
    let name: String?

    enum CodingKeys: String, CodingKey {
        case id = "Id"
        case name = "Name"
    }
}

struct AuthenticationResult: Decodable, Sendable {
    let user: UserDto
    let accessToken: String
    let serverId: String?

    enum CodingKeys: String, CodingKey {
        case user = "User"
        case accessToken = "AccessToken"
        case serverId = "ServerId"
    }
}
