import SwiftUI

/// Detail screen for titles that are not in the library yet. It lets the user
/// request the title and follows `/request/queue` until the queue reports
/// download progress.
struct RequestDetailView: View {
    @Environment(AppEnvironment.self) private var env
    let item: RecommendationItem
    @State private var model = RequestDetailViewModel()

    var body: some View {
        ScrollView(.vertical, showsIndicators: false) {
            ZStack(alignment: .bottomLeading) {
                GeometryReader { geo in
                    RemoteImage(url: item.backdropUrl.flatMap { URL(string: $0) } ?? item.posterUrl.flatMap { URL(string: $0) })
                        .frame(width: geo.size.width, height: geo.size.height)
                        .clipped()
                        .accessibilityHidden(true)
                }
                LinearGradient(colors: [.clear, Theme.bg], startPoint: .center, endPoint: .bottom)
                LinearGradient(
                    colors: [Theme.bg.opacity(Theme.Opacity.scrimHeader), Theme.bg.opacity(Theme.Opacity.scrimHeaderMid), .clear],
                    startPoint: .leading, endPoint: UnitPoint(x: 0.65, y: 0.5)
                )

                VStack(alignment: .leading, spacing: 18) {
                    Text(item.title)
                        .font(.system(size: 60, weight: .heavy))
                        .lineLimit(2)
                        .foregroundStyle(Theme.textPrimary)

                    HStack(spacing: 18) {
                        if let year = item.year { meta(String(year)) }
                        meta(item.type == "Series" ? "Serie" : "Film")
                        if let imdb = item.communityRating { meta("IMDb \(String(format: "%.1f", imdb))") }
                        if let rt = item.criticRating { meta("RT \(Int(rt))%") }
                    }

                    if let overview = item.overview, !overview.isEmpty {
                        Text(overview)
                            .font(.system(size: 24))
                            .foregroundStyle(Theme.textDim)
                            .lineLimit(5)
                            .frame(maxWidth: 980, alignment: .leading)
                    }

                    statusPanel
                        .padding(.top, 16)
                }
                .padding(.horizontal, Theme.screenPadding)
                .padding(.bottom, 50)
            }
            .frame(height: Theme.detailHeaderHeight)
        }
        .scrollClipDisabled()
        .background(Theme.bg)
        .ignoresSafeArea(edges: .top)
        .task { await model.refreshQueue(env: env, matching: item) }
    }

    private var statusPanel: some View {
        VStack(alignment: .leading, spacing: 14) {
            switch model.state {
            case .requestable:
                Button {
                    Task { await model.request(item, env: env) }
                } label: {
                    Label("Anfragen", systemImage: "arrow.down.circle.fill")
                }
                .disabled(model.isWorking)
            case .requesting:
                Label("Anfrage wird gesendet …", systemImage: "paperplane.fill")
                    .font(.system(size: 23, weight: .bold))
                    .foregroundStyle(Theme.textPrimary)
            case .loading(let progress, let detail):
                VStack(alignment: .leading, spacing: 10) {
                    Label("Lädt", systemImage: "arrow.down.circle.fill")
                        .font(.system(size: 23, weight: .bold))
                        .foregroundStyle(Theme.textPrimary)
                    ProgressView(value: progress)
                        .frame(width: 460)
                    Text(detail ?? "\(Int(progress * 100))%")
                        .font(.system(size: 18, weight: .semibold))
                        .foregroundStyle(Theme.textDim)
                }
            case .available:
                Label("Vorhanden", systemImage: "checkmark.circle.fill")
                    .font(.system(size: 23, weight: .bold))
                    .foregroundStyle(Theme.accent)
            case .failed(let message):
                VStack(alignment: .leading, spacing: 12) {
                    StatusView(kind: .error(message))
                    Button("Erneut versuchen") {
                        Task { await model.request(item, env: env) }
                    }
                    .disabled(model.isWorking)
                }
            }
        }
        .task(id: model.shouldPollQueue) {
            guard model.shouldPollQueue else { return }
            await model.pollQueue(env: env, matching: item)
        }
    }

    private func meta(_ text: String) -> some View {
        Text(text)
            .font(.system(size: 23))
            .foregroundStyle(Theme.textDim)
    }
}
