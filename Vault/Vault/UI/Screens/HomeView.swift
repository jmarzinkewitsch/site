import SwiftUI

/// Home: large focus-driven stage preview on top, shelves below.
/// Moving focus through the shelves crossfades the stage to the focused
/// item's backdrop. Click opens details, play/pause starts playback directly.
struct HomeView: View {
    @Environment(AppEnvironment.self) private var env
    @State private var model = HomeViewModel()
    @State private var stageItem: BaseItemDto?
    @State private var playerItem: PlayerItem?
    @State private var scrollY: CGFloat = 0
    @FocusState private var focusedID: String?

    /// Distance (pts) over which the stage fades out as the user scrolls, so
    /// the shelves land on the solid background instead of overlapping the
    /// fixed hero backdrop and its text.
    private let stageFadeDistance: CGFloat = 280

    var body: some View {
        ZStack(alignment: .top) {
            Theme.bg.ignoresSafeArea()

            let currentStageItem = stageItem ?? model.resume.first ?? model.latestMovies.first
            let stageOpacity = max(0, 1 - max(0, scrollY) / stageFadeDistance)

            // Full-bleed backdrop behind the whole screen — stage, shelves and
            // (through the bar material) the menu bar. Stays put while scrolling,
            // crossfades to the focused item, darkens as the shelves come up.
            BackdropView(
                item: currentStageItem,
                imageURL: stageImageURL(for: currentStageItem),
                scrollY: scrollY
            )

            // Stage info on top of the backdrop; fades out as the user scrolls so
            // it never collides with the shelves.
            StageView(item: currentStageItem)
                .opacity(stageOpacity)

            ScrollView(.vertical, showsIndicators: false) {
                VStack(alignment: .leading, spacing: 44) {
                    Color.clear.frame(height: Theme.stageHeight)

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
            }
            .scrollClipDisabled()
            .onScrollGeometryChange(for: CGFloat.self) { geo in
                geo.contentOffset.y + geo.contentInsets.top
            } action: { _, offset in
                scrollY = max(0, offset)
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
