import SwiftUI

/// "Für dich": personalised recommendations from vault-api (/recommend).
/// Two shelves — requestable titles ("Für dich neu") and owned titles
/// ("Aus deiner Bibliothek"). Owned items open details / play; new items can
/// open a request detail screen with queue progress from Radarr/Sonarr.
struct ForYouView: View {
    @Environment(AppEnvironment.self) private var env
    @State private var model = ForYouViewModel()
    @State private var playerItem: PlayerItem?
    @FocusState private var focusedID: String?

    var body: some View {
        ScrollView(.vertical, showsIndicators: false) {
            VStack(alignment: .leading, spacing: 44) {
                header

                if model.isLoading && model.isEmpty {
                    SkeletonShelf(posterStyle: true)
                    SkeletonShelf(posterStyle: true)
                } else if let error = model.errorMessage {
                    StatusView(kind: .error(error))
                        .padding(.horizontal, Theme.screenPadding)
                } else if model.isEmpty {
                    StatusView(kind: .empty("Noch keine Empfehlungen — bewerte ein paar Titel und schau später wieder rein."))
                        .padding(.horizontal, Theme.screenPadding)
                } else {
                    profileTabs

                    ForEach(model.visibleShelves) { shelf in
                        if !shelf.items.isEmpty {
                            MediaShelf(title: shelf.title) {
                                ForEach(shelf.items) { item in
                                    recCard(item)
                                }
                            }
                        }
                    }
                }

                Color.clear.frame(height: 60)
            }
            .padding(.top, Theme.chromeContentTopPadding)
        }
        .scrollClipDisabled()
        .background(Theme.bg)
        .ignoresSafeArea()
        .task { if model.shelves.isEmpty { await model.load(env: env) } }
        .navigationDestination(for: LibraryRef.self) { ref in
            RecommendationDetailLoader(libraryId: ref.id)
        }
        .fullScreenCover(item: $playerItem) { item in
            PlayerScreen(item: item, reporter: env.reporter)
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Empfehlungen")
                .font(.system(size: 44, weight: .bold))
                .foregroundStyle(Theme.textPrimary)
            if model.llmUsed {
                Label("Von Claude personalisiert", systemImage: "sparkles")
                    .font(.system(size: 18))
                    .foregroundStyle(Theme.textDim)
            }
        }
        .padding(.horizontal, Theme.screenPadding)
    }

    private var profileTabs: some View {
        HStack(spacing: 16) {
            ForEach(model.profileTabs, id: \.id) { tab in
                Button(tab.title) { model.selectedProfile = tab.id }
                    .foregroundStyle(model.selectedProfile == tab.id ? Theme.accentText : Theme.textPrimary)
                    .padding(.horizontal, 18)
                    .padding(.vertical, 10)
                    .background(model.selectedProfile == tab.id ? Theme.accent : Theme.bg.opacity(0.4), in: Capsule())
            }
        }
        .padding(.horizontal, Theme.screenPadding)
    }

    @ViewBuilder
    private func recCard(_ item: RecommendationItem) -> some View {
        let card = RecommendationCard(
            item: item,
            imageURL: item.posterUrl.flatMap { URL(string: $0) },
            isRequesting: model.isRequesting(item)
        )
        if item.isPlayable, let libraryId = item.libraryId {
            NavigationLink(value: LibraryRef(id: libraryId)) { card }
                .buttonStyle(CardButtonStyle())
                .focused($focusedID, equals: item.id)
                .onPlayPauseCommand { Task { await play(libraryId: libraryId) } }
        } else {
            NavigationLink {
                RequestDetailView(item: item)
            } label: {
                card
            }
            .buttonStyle(CardButtonStyle())
            .focused($focusedID, equals: item.id)
        }
    }

    private func play(libraryId: String) async {
        guard let library = env.library, let base = try? await library.item(id: libraryId) else { return }
        playerItem = await env.playerItem(for: base, resume: base.resumePositionSeconds > 1)
    }
}

/// Navigation value for opening an owned recommendation's detail by library id.
private struct LibraryRef: Hashable { let id: String }

/// Fetches a library item by id, then shows its detail. Used because a
/// recommendation only carries the library id, not a full item.
private struct RecommendationDetailLoader: View {
    @Environment(AppEnvironment.self) private var env
    let libraryId: String
    @State private var item: BaseItemDto?
    @State private var errorMessage: String?

    var body: some View {
        Group {
            if let item {
                ItemDetailView(summary: item)
            } else if let errorMessage {
                StatusView(kind: .error(errorMessage))
                    .padding(.horizontal, Theme.screenPadding)
            } else {
                StatusView(kind: .loading("Lädt …"))
                    .padding(.horizontal, Theme.screenPadding)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Theme.bg)
        .task { await load() }
    }

    private func load() async {
        guard let library = env.library else { return }
        do {
            item = try await library.item(id: libraryId)
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
