import SwiftUI

struct RootTabView: View {
    @Environment(AppEnvironment.self) private var env
    @State private var homePath: [BaseItemDto] = []

    var body: some View {
        @Bindable var env = env

        TabView(selection: $env.selectedTab) {
            NavigationStack(path: $homePath) { HomeView(navigationPath: $homePath) }
                .tabItem { Text("Home") }
                .tag(0)
            NavigationStack { LibraryGridView(kind: .movie, title: "Filme") }
                .tabItem { Text("Filme") }
                .tag(1)
            NavigationStack { LibraryGridView(kind: .series, title: "Serien") }
                .tabItem { Text("Serien") }
                .tag(2)
            NavigationStack { SettingsView(isOnboarding: false) }
                .tabItem { Text("Einstellungen") }
                .tag(3)
        }
        .background(Theme.bg)
    }
}
