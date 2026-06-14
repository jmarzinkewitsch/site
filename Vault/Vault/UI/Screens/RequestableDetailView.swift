import SwiftUI

/// Detail screen for recommendation/search titles that are not in Jellyfin yet.
/// It follows the mockup's requestable → loading → available states and polls
/// `/request/queue` for live Radarr/Sonarr progress after a request is sent.
struct RequestableDetailView: View {
    @Environment(AppEnvironment.self) private var env
    let item: RecommendationItem
    @State private var model = RequestableDetailViewModel()
    @State private var playerItem: PlayerItem?

    var body: some View {
        ScrollView(.vertical, showsIndicators: false) {
            ZStack(alignment: .bottomLeading) {
                backdrop
                LinearGradient(colors: [.clear, Theme.bg], startPoint: .center, endPoint: .bottom)
                LinearGradient(
                    colors: [Theme.bg.opacity(Theme.Opacity.scrimHeader), Theme.bg.opacity(Theme.Opacity.scrimHeaderMid), .clear],
                    startPoint: .leading,
                    endPoint: UnitPoint(x: 0.65, y: 0.5)
                )
                content
            }
            .frame(height: Theme.detailHeaderHeight)

            if let error = model.errorMessage {
                StatusView(kind: .error(error))
                    .padding(.horizontal, Theme.screenPadding)
            }
        }
        .scrollClipDisabled()
        .background(Theme.bg)
        .ignoresSafeArea(edges: .top)
        .task(id: item.id) { await pollQueue() }
        .fullScreenCover(item: $playerItem) { item in
            PlayerScreen(item: item, reporter: env.reporter)
        }
    }

    private var backdrop: some View {
        GeometryReader { geo in
            RemoteImage(url: item.backdropUrl.flatMap(URL.init(string:)) ?? item.posterUrl.flatMap(URL.init(string:)))
                .frame(width: geo.size.width, height: geo.size.height)
                .clipped()
                .accessibilityHidden(true)
        }
    }

    private var content: some View {
        VStack(alignment: .leading, spacing: 18) {
            Text(kicker)
                .font(.system(size: 22, weight: .bold))
                .kerning(2)
                .foregroundStyle(kickerColor)

            Text(item.title)
                .font(.system(size: 60, weight: .heavy))
                .lineLimit(2)
                .foregroundStyle(Theme.textPrimary)

            HStack(spacing: 18) {
                if let year = item.year { meta(String(year)) }
                meta(item.type.lowercased() == "series" ? "Serie" : "Film")
            }

            scoreBadges

            if let overview = item.overview, !overview.isEmpty {
                Text(overview)
                    .font(.system(size: 24))
                    .foregroundStyle(Theme.textDim)
                    .lineLimit(4)
                    .frame(maxWidth: 980, alignment: .leading)
            }

            requestStatus
                .padding(.top, 8)
        }
        .padding(.horizontal, Theme.screenPadding)
        .padding(.bottom, 50)
    }

    private var kicker: String {
        switch model.state {
        case .requestable: return "\(item.typeLabel.uppercased()) · NICHT IN DER BIBLIOTHEK"
        case .requesting: return "ANFRAGE WIRD GESENDET"
        case .downloading: return "ANGEFRAGT · LÄDT"
        case .requestedWaiting: return "ANGEFRAGT · WARTET AUF QUEUE"
        case .available: return "VORHANDEN"
        }
    }

    private var kickerColor: Color {
        switch model.state {
        case .requestable, .requesting, .requestedWaiting: return Theme.accent
        case .downloading, .available: return .green
        }
    }

    @ViewBuilder
    private var requestStatus: some View {
        switch model.state {
        case .requestable:
            HStack(spacing: 28) {
                Button { Task { await model.request(item, env: env) } } label: {
                    Label("Anfragen", systemImage: "plus")
                }
                Button("Trailer") {}
                    .disabled(true)
            }
        case .requesting:
            HStack(spacing: 14) {
                ProgressView()
                Text("Anfrage wird an \(item.type.lowercased() == "series" ? "Sonarr" : "Radarr") gesendet …")
                    .font(.system(size: 21, weight: .semibold))
                    .foregroundStyle(Theme.textDim)
            }
        case .downloading(let queueItem):
            VStack(alignment: .leading, spacing: 12) {
                ProgressView(value: queueItem.clampedProgress)
                    .frame(width: 560)
                    .tint(Theme.accent)
                Text(queueNote(queueItem))
                    .font(.system(size: 20, weight: .semibold))
                    .foregroundStyle(Theme.textDim)
                Button("Anfrage abbrechen") {}
                    .disabled(true)
                    .padding(.top, 6)
            }
        case .requestedWaiting:
            HStack(spacing: 14) {
                ProgressView()
                Text(model.requestMessage ?? "Angefragt — warte auf Queue-Fortschritt …")
                    .font(.system(size: 21, weight: .semibold))
                    .foregroundStyle(Theme.textDim)
            }
        case .available(let libraryId):
            Button { Task { await play(libraryId: libraryId) } } label: {
                Label("Abspielen", systemImage: "play.fill")
            }
            .disabled(libraryId == nil)
        }
    }

    private var scoreBadges: some View {
        HStack(spacing: 12) {
            if let imdb = item.communityRating {
                scoreBadge(label: "IMDb", value: String(format: "%.1f", imdb))
            }
            if let rt = item.criticRating {
                scoreBadge(label: "RT", value: "\(Int(rt))%")
            }
        }
        .frame(height: 34)
    }

    private func scoreBadge(label: String, value: String) -> some View {
        HStack(spacing: 6) {
            Text(label).foregroundStyle(Theme.textDim)
            Text(value).foregroundStyle(Theme.textPrimary)
        }
        .font(.system(size: 18, weight: .bold))
        .padding(.horizontal, 12)
        .padding(.vertical, 7)
        .background(Theme.bg.opacity(0.55), in: Capsule())
        .overlay(Capsule().stroke(Theme.textDim.opacity(0.35), lineWidth: 1))
    }

    private func queueNote(_ queueItem: RequestQueueItem) -> String {
        let status = queueItem.status ?? (item.type.lowercased() == "series" ? "Sonarr" : "Radarr")
        if let timeLeft = queueItem.timeLeft, !timeLeft.isEmpty {
            return "\(queueItem.progressPercent) % · noch ca. \(timeLeft) · \(status)"
        }
        return "\(queueItem.progressPercent) % · \(status)"
    }

    private func play(libraryId: String?) async {
        guard let libraryId, let library = env.library, let base = try? await library.item(id: libraryId) else { return }
        playerItem = await env.playerItem(for: base, resume: base.resumePositionSeconds > 1)
    }

    private func meta(_ text: String) -> some View {
        Text(text)
            .font(.system(size: 23))
            .foregroundStyle(Theme.textDim)
    }

    private func pollQueue() async {
        await model.refreshQueue(for: item, env: env)
        while !Task.isCancelled {
            try? await Task.sleep(for: .seconds(5))
            await model.refreshQueue(for: item, env: env)
        }
    }
}

private extension RecommendationItem {
    var typeLabel: String { type.lowercased() == "series" ? "Serie" : "Film" }
}
