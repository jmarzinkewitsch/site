import SwiftUI

/// Paged poster grid for the Movies and Series tabs.
struct LibraryGridView: View {
    @Environment(AppEnvironment.self) private var env
    @State private var model: LibraryViewModel
    let title: String

    init(kind: ItemKind, title: String) {
        self.title = title
        _model = State(initialValue: LibraryViewModel(kind: kind))
    }

    private let columns = Array(
        repeating: GridItem(.flexible(), spacing: 48), count: 6
    )

    var body: some View {
        ScrollView(.vertical, showsIndicators: false) {
            VStack(alignment: .leading, spacing: 24) {
                HStack(alignment: .firstTextBaseline, spacing: 20) {
                    Text(title)
                        .font(.system(size: 44, weight: .bold))
                        .foregroundStyle(Theme.textPrimary)
                    if let total = model.totalCount {
                        Text("\(total) Titel")
                            .font(.system(size: 24))
                            .foregroundStyle(Theme.textDim)
                    }
                }
                .padding(.horizontal, Theme.screenPadding)

                if let error = model.errorMessage {
                    StatusView(kind: .error(error))
                        .padding(.horizontal, Theme.screenPadding)
                } else if model.isInitialLoading {
                    StatusView(kind: .loading("Lädt …"))
                        .padding(.horizontal, Theme.screenPadding)
                } else if model.isEmpty {
                    StatusView(kind: .empty("Keine Titel in dieser Bibliothek."))
                        .padding(.horizontal, Theme.screenPadding)
                }

                LazyVGrid(columns: columns, alignment: .leading, spacing: 56) {
                    ForEach(model.items) { item in
                        NavigationLink(value: item) {
                            PosterCard(item: item, imageURL: env.posterURL(for: item), width: 220)
                        }
                        .buttonStyle(CardButtonStyle(scale: 1.08))
                        .onAppear {
                            if item.id == model.items.last?.id {
                                Task { await model.loadNextPage(env: env) }
                            }
                        }
                    }
                }
                .padding(.horizontal, Theme.screenPadding)
                .padding(.vertical, 30)

                // Footer spinner while the next page is fetched during infinite scroll.
                if model.isLoadingPage && !model.items.isEmpty {
                    StatusView(kind: .loading("Mehr laden …"))
                        .padding(.horizontal, Theme.screenPadding)
                        .padding(.bottom, 30)
                        .frame(maxWidth: .infinity)
                }
            }
            .padding(.top, Theme.chromeContentTopPadding)
        }
        .scrollClipDisabled()
        .background(Theme.bg)
        .ignoresSafeArea()
        .task { await model.loadInitial(env: env) }
        .navigationDestination(for: BaseItemDto.self) { item in
            ItemDetailView(summary: item)
        }
    }
}
