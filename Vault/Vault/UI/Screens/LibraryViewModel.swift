import Foundation
import Observation

@Observable
final class LibraryViewModel {
    let kind: ItemKind
    var items: [BaseItemDto] = []
    var totalCount: Int?
    var errorMessage: String?
    private(set) var isLoadingPage = false
    private let pageSize = 100

    /// True only before the very first page has arrived (drives the full-screen loader).
    var isInitialLoading: Bool { isLoadingPage && items.isEmpty }

    /// No results after a completed, error-free load.
    var isEmpty: Bool { items.isEmpty && !isLoadingPage && errorMessage == nil }

    init(kind: ItemKind) {
        self.kind = kind
    }

    var canLoadMore: Bool {
        guard let total = totalCount else { return items.isEmpty }
        return items.count < total
    }

    @MainActor
    func loadInitial(env: AppEnvironment) async {
        guard items.isEmpty else { return }
        await loadNextPage(env: env)
    }

    @MainActor
    func loadNextPage(env: AppEnvironment) async {
        guard let library = env.library, !isLoadingPage, canLoadMore else { return }
        isLoadingPage = true
        defer { isLoadingPage = false }
        do {
            let page = try await library.items(kind: kind, startIndex: items.count, limit: pageSize)
            // Guard against duplicates when a page request races a refresh.
            let known = Set(items.map(\.id))
            items.append(contentsOf: page.items.filter { !known.contains($0.id) })
            totalCount = page.totalRecordCount
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
