import Foundation

enum AppGroup {
    static let identifier = "group.de.marzinkewitsch.vault"

    static var defaults: UserDefaults {
        UserDefaults(suiteName: identifier) ?? .standard
    }
}
