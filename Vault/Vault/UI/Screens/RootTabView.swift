import SwiftUI

struct RootTabView: View {
    var body: some View {
        TabView {
            NavigationStack { HomeView() }
                .tabItem { Text("Home") }
            NavigationStack { LibraryGridView(kind: .movie, title: "Filme") }
                .tabItem { Text("Filme") }
            NavigationStack { LibraryGridView(kind: .series, title: "Serien") }
                .tabItem { Text("Serien") }
            NavigationStack { SettingsView(isOnboarding: false) }
                .tabItem { Text("Einstellungen") }
        }
        .background(Theme.bg)
    }
}
