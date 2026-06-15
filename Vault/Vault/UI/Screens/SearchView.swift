import SwiftUI

/// Search across owned Jellyfin library items and requestable TMDB titles.
struct SearchView: View {
    @Environment(AppEnvironment.self) private var env
    @State private var model = SearchViewModel()
    @FocusState private var focusedID: String?

    private let columns = [GridItem(.adaptive(minimum: Theme.posterWidth), spacing: 32)]

    var body: some View {
        ScrollView(.vertical, showsIndicators: false) {
            VStack(alignment: .leading, spacing: 32) {
                header
                stateContent
                Color.clear.frame(height: 60)
            }
            .padding(.top, 100)
            .padding(.horizontal, Theme.screenPadding)
        }
        .scrollClipDisabled()
        .background(Theme.bg)
        .onChange(of: model.query) { _, _ in model.queryChanged(env: env) }
        .navigationDestination(for: SearchLibraryRef.self) { ref in
            SearchDetailLoader(libraryId: ref.id)
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 18) {
            Text("Suche")
                .font(.system(size: 44, weight: .bold))
                .foregroundStyle(Theme.textPrimary)
            TextField("Filme und Serien suchen", text: $model.query)
                .textInputAutocapitalization(.words)
                .disableAutocorrection(true)
                .font(.system(size: 30, weight: .semibold))
                .padding(.horizontal, 24)
                .padding(.vertical, 18)
                .background(Theme.bg.opacity(0.45), in: RoundedRectangle(cornerRadius: Theme.cornerRadius))
        }
    }

    @ViewBuilder
    private var stateContent: some View {
        if !model.hasQuery {
            StatusView(kind: .empty("Gib einen Suchbegriff ein, um Bibliothek und neue Titel zu durchsuchen."))
        } else if model.isLoading && model.results.isEmpty {
            StatusView(kind: .loading("Suche läuft …"))
        } else if let error = model.errorMessage {
            StatusView(kind: .error(error))
        } else if model.results.isEmpty {
            StatusView(kind: .empty("Keine Treffer gefunden."))
        } else {
            LazyVGrid(columns: columns, alignment: .leading, spacing: 42) {
                ForEach(model.results) { item in
                    resultCard(item)
                }
            }
        }
    }

    @ViewBuilder
    private func resultCard(_ item: SearchItem) -> some View {
        let card = SearchResultCard(item: item)
        if item.isPlayable, let libraryId = item.libraryId {
            NavigationLink(value: SearchLibraryRef(id: libraryId)) { card }
                .buttonStyle(CardButtonStyle())
                .focused($focusedID, equals: item.id)
        } else {
            NavigationLink { RequestDetailView(item: item.requestItem) } label: { card }
                .buttonStyle(CardButtonStyle())
                .focused($focusedID, equals: item.id)
        }
    }
}

private struct SearchResultCard: View {
    let item: SearchItem
    private let width = Theme.posterWidth

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            ZStack(alignment: .topTrailing) {
                RemoteImage(url: item.posterUrl.flatMap { URL(string: $0) })
                    .frame(width: width, height: width * Theme.posterAspectRatio)
                    .clipShape(RoundedRectangle(cornerRadius: Theme.cornerRadius))
                    .modifier(FocusRing())
                    .accessibilityHidden(true)
                statusPill.padding(8)
            }
            Text(item.title)
                .font(.system(size: 22, weight: .semibold))
                .lineLimit(1)
                .foregroundStyle(Theme.textPrimary)
            HStack(spacing: 10) {
                if let year = item.year { meta(String(year)) }
                meta(item.type == "Series" ? "Serie" : "Film")
            }
        }
        .frame(width: width, alignment: .leading)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(accessibilityLabel)
    }

    private var statusPill: some View {
        Label(item.isPlayable ? "Abspielen" : "Anfragen", systemImage: item.isPlayable ? "play.fill" : "plus.circle.fill")
            .labelStyle(.titleAndIcon)
            .font(.system(size: 15, weight: .bold))
            .foregroundStyle(Theme.accentText)
            .padding(.horizontal, 10)
            .padding(.vertical, 5)
            .background(Theme.accent, in: Capsule())
    }

    private func meta(_ text: String) -> some View {
        Text(text).font(.system(size: 18)).foregroundStyle(Theme.textDim)
    }

    private var accessibilityLabel: String {
        var parts = [item.title]
        if let year = item.year { parts.append(String(year)) }
        parts.append(item.isPlayable ? "abspielbar" : "anfragbar")
        return parts.joined(separator: ", ")
    }
}

private struct SearchLibraryRef: Hashable { let id: String }

private struct SearchDetailLoader: View {
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
            } else {
                StatusView(kind: .loading("Lädt …"))
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
