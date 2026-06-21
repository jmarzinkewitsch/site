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

            let currentStageItem = stageItem ?? model.resume.first ?? model.latestMovies.first

            // Full-bleed backdrop behind the whole screen — stage, shelves and
            // (through the bar material) the menu bar. Crossfades to the focused item.
            BackdropView(
                item: currentStageItem,
                imageURL: stageImageURL(for: currentStageItem)
            )

            VStack(spacing: 0) {
                // Stage stays pinned at the top — always visible with logo + details.
                StageView(item: currentStageItem)
                    .frame(height: Theme.stageHeight, alignment: .topLeading)

                // Shelves scroll in the band below the stage; only ~one shelf is
                // visible at a time while the stage above never moves.
                ScrollView(.vertical, showsIndicators: false) {
                    VStack(alignment: .leading, spacing: 44) {
                        if model.isLoading && model.isEmpty {
                            SkeletonShelf(posterStyle: false)
                            SkeletonShelf(posterStyle: true)
                        }

                        if !model.continueWatching.isEmpty {
                            MediaShelf(title: "Weiterschauen") {
                                ForEach(model.continueWatching) { item in
                                    shelfCard(item) {
                                        ContinueWatchingCard(item: item, imageURL: continueImageURL(for: item))
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

                        if !model.seasonal.isEmpty {
                            MediaShelf(title: model.seasonalTitle) {
                                ForEach(model.seasonal) { item in
                                    shelfCard(item) {
                                        PosterCard(item: item, imageURL: env.posterURL(for: item))
                                    }
                                }
                            }
                        }

                        if !model.topRated.isEmpty {
                            MediaShelf(title: "Bestbewertet") {
                                ForEach(model.topRated) { item in
                                    shelfCard(item) {
                                        PosterCard(item: item, imageURL: env.posterURL(for: item))
                                    }
                                }
                            }
                        }

                        if !model.discover.isEmpty {
                            MediaShelf(title: "Noch nicht gesehen") {
                                ForEach(model.discover) { item in
                                    shelfCard(item) {
                                        PosterCard(item: item, imageURL: env.posterURL(for: item))
                                    }
                                }
                            }
                        }

                        if let error = model.errorMessage {
                            StatusView(kind: .error(error))
                                .padding(.leading, Theme.screenPadding)
                        } else if model.isEmpty && !model.isLoading {
                            StatusView(kind: .empty("Keine Inhalte gefunden — Bibliothek leer oder Server nicht erreichbar."))
                                .padding(.leading, Theme.screenPadding)
                        }

                        Color.clear.frame(height: 60)
                    }
                    .padding(.top, 24)
                }
            }
        }
        .ignoresSafeArea()
        .task { await model.load(env: env) }
        .onChange(of: focusedID) { _, newID in
            if let newID, let item = model.item(withID: newID) {
                stageItem = item
            }
        }
        .navigationDestination(for: BaseItemDto.self) { item in
            ItemDetailView(summary: item)
        }
        .fullScreenCover(item: $playerItem, onDismiss: {
            Task { await model.load(env: env) }
        }) { item in
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

    /// Landscape artwork for the merged shelf: episode → season backdrop when
    /// available (next-up episodes often lack their own), else the item backdrop.
    private func continueImageURL(for item: BaseItemDto) -> URL? {
        if item.kind == .episode, let raw = model.seasonBackdropURLsByEpisodeID[item.id] {
            return env.reachableMediaURL(from: raw)
        }
        return env.backdropURL(for: item)
    }

    private func stageImageURL(for item: BaseItemDto?) -> URL? {
        guard let item else { return nil }
        if item.kind == .episode,
           let raw = model.seasonBackdropURLsByEpisodeID[item.id] {
            return env.reachableMediaURL(from: raw)
        }
        return env.backdropURL(for: item)
    }
}
