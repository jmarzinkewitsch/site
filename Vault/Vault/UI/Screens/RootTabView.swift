import SwiftUI

struct RootTabView: View {
    @Environment(AppEnvironment.self) private var env
    @State private var homePath: [BaseItemDto] = []

    var body: some View {
        @Bindable var env = env

        TabView(selection: $env.selectedTab) {
            NavigationStack(path: $homePath) { HomeView() }
                .tabItem { Text("Home") }
                .tag(RootTab.home)
            NavigationStack { LibraryGridView(kind: .movie, title: "Filme") }
                .tabItem { Text("Filme") }
                .tag(RootTab.movies)
            NavigationStack { LibraryGridView(kind: .series, title: "Serien") }
                .tabItem { Text("Serien") }
                .tag(RootTab.series)
            NavigationStack { SettingsView(isOnboarding: false) }
                .tabItem { Text("Einstellungen") }
                .tag(RootTab.settings)
        }
        .background(Theme.bg)
        .onChange(of: env.pendingDetailItem) { _, item in
            guard let item else { return }
            homePath = [item]
            env.pendingDetailItem = nil
        }
        .fullScreenCover(item: $env.pendingPlayerItem) { item in
            PlayerScreen(item: item, reporter: env.reporter)
        }
    }
}
