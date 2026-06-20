import SwiftUI

@main
struct VaultApp: App {
    @State private var env = AppEnvironment()
    @State private var showIntro = true

    var body: some Scene {
        WindowGroup {
            ZStack {
                Group {
                    if env.isConfigured {
                        RootTabView()
                    } else {
                        SettingsView(isOnboarding: true)
                    }
                }

                if showIntro {
                    VaultIntroView {
                        withAnimation(.easeOut(duration: 0.35)) { showIntro = false }
                    }
                    .transition(.opacity)
                    .zIndex(1)
                }
            }
            .environment(env)
            .preferredColorScheme(.dark)
            .onOpenURL { env.handleOpenURL($0) }
        }
    }
}
