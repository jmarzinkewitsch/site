import SwiftUI

@main
struct VaultApp: App {
    @State private var env = AppEnvironment()
    @State private var listener: CastListener
    @State private var showIntro = true
    @Environment(\.scenePhase) private var scenePhase

    init() {
        let env = AppEnvironment()
        _env = State(initialValue: env)
        _listener = State(initialValue: CastListener(env: env))
    }

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
            // Start the cast listener at launch and whenever the app returns to
            // the foreground (the kiosk cast is what brings the app forward, so
            // .active is exactly when a pending command is waiting). Stop it in
            // the background to avoid pointless polling.
            .task { listener.start() }
            .onChange(of: scenePhase) { _, phase in
                switch phase {
                case .active:
                    listener.start()
                case .background, .inactive:
                    listener.stop()
                @unknown default:
                    break
                }
            }
        }
    }
}
