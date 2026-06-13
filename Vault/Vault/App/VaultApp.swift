import SwiftUI

@main
struct VaultApp: App {
    @State private var env = AppEnvironment()

    var body: some Scene {
        WindowGroup {
            Group {
                if env.isConfigured {
                    RootTabView()
                } else {
                    SettingsView(isOnboarding: true)
                }
            }
            .environment(env)
            .preferredColorScheme(.dark)
        }
    }
}
