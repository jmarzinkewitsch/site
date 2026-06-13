import SwiftUI

/// Home: large focus-driven stage preview on top, shelves below.
/// Moving focus through the shelves crossfades the stage to the focused
/// item's backdrop. Click opens details, play/pause starts playback directly.
struct HomeView: View {
    @Environment(AppEnvironment.self) private var env
    @State private var model = HomeViewModel()
    @State private var stageItem: BaseItemDto?
    @State private var playerItem: PlayerItem?
    @FocusState private var focusedID: String?

    var body: some View {
        ZStack(alignment: .top) {
            Theme.bg.ignoresSafeArea()

            StageView(item: stageItem ?? model.resume.first ?? model.latestMovies.first)

            VaultTopBar()

            ScrollView(.vertical, showsIndicators: false) {
                VStack(alignment: .leading, spacing: 44) {
                    Color.clear.frame(height: Theme.stageHeight - 80)

                    if !model.resume.isEmpty {
                        MediaShelf(title: "Weiterschauen") {
                            ForEach(model.resume) { item in
                                shelfCard(item) {
                                    ContinueWatchingCard(item: item, imageURL: env.backdropURL(for: item, maxWidth: 800))
                                }
                            }
                        }
                    }

                    if !model.nextUp.isEmpty {
                        MediaShelf(title: "Nächste Episoden") {
                            ForEach(model.nextUp) { item in
                                shelfCard(item) {
                                    ContinueWatchingCard(item: item, imageURL: env.backdropURL(for: item, maxWidth: 800))
                                }
                            }
                        }
                    }

                    if !model.latestMovies.isEmpty {
                        MediaShelf(title: "Neue Filme") {
                            ForEach(model.latestMovies) { item in
                                shelfCard(item) {
                                    PosterCard(item: item, imageURL: env.posterURL(for: item))
                                }
                            }
                        }
                    }

                    if !model.latestSeries.isEmpty {
                        MediaShelf(title: "Neue Serien") {
                            ForEach(model.latestSeries) { item in
                                shelfCard(item) {
                                    PosterCard(item: item, imageURL: env.posterURL(for: item))
                                }
                            }
                        }
                    }

                    if let error = model.errorMessage {
                        Label(error, systemImage: "exclamationmark.triangle.fill")
                            .foregroundStyle(.red)
                            .padding(.leading, Theme.screenPadding)
                    } else if model.isEmpty && !model.isLoading {
                        Text("Keine Inhalte gefunden — Bibliothek leer oder Server nicht erreichbar.")
                            .foregroundStyle(Theme.textDim)
                            .padding(.leading, Theme.screenPadding)
                    }

                    Color.clear.frame(height: 60)
                }
            }
            .scrollClipDisabled()
        }
        .ignoresSafeArea(edges: .top)
        .task { await model.load(env: env) }
        .onChange(of: focusedID) { _, newID in
            if let newID, let item = model.item(withID: newID) {
                stageItem = item
            }
        }
        .navigationDestination(for: BaseItemDto.self) { item in
            ItemDetailView(summary: item)
        }
        .fullScreenCover(item: $playerItem) { item in
            PlayerScreen(item: item, reporter: env.reporter)
        }
    }

    /// Wraps shelf content in a NavigationLink (click → details), reports
    /// focus for the stage, and starts direct playback on the play/pause key.
    @ViewBuilder
    private func shelfCard<Label: View>(_ item: BaseItemDto, @ViewBuilder label: () -> Label) -> some View {
        NavigationLink(value: item) {
            label()
        }
        .buttonStyle(CardButtonStyle())
        .focused($focusedID, equals: item.id)
        .onPlayPauseCommand {
            Task { playerItem = await env.playerItem(for: item, resume: true) }
        }
    }
}


private struct VaultTopBar: View {
    var body: some View {
        HStack(alignment: .center) {
            Text("◆ VAULT")
                .font(.system(size: 31, weight: .heavy))
                .kerning(6)
                .foregroundStyle(Theme.accent)

            Spacer()

            HStack(spacing: 64) {
                topTab("Home", active: true)
                topTab("Filme")
                topTab("Serien")
                topTab("Einstellungen")
            }

            Spacer()

            Text(Date.now, style: .time)
                .font(.system(size: 23, weight: .medium, design: .rounded))
                .foregroundStyle(Theme.textDim)
                .monospacedDigit()
        }
        .padding(.horizontal, Theme.screenPadding)
        .frame(height: 104)
        .background(LinearGradient(colors: [Theme.bg.opacity(0.7), .clear], startPoint: .top, endPoint: .bottom))
    }

    private func topTab(_ title: String, active: Bool = false) -> some View {
        VStack(spacing: 8) {
            Text(title)
                .font(.system(size: 25, weight: .semibold))
                .foregroundStyle(active ? Theme.textPrimary : Theme.textDim)
            Capsule()
                .fill(active ? Theme.accent : .clear)
                .frame(width: 42, height: 4)
        }
    }
}
