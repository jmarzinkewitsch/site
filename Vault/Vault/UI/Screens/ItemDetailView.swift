import SwiftUI

/// Detail screen for movies, series and episodes. Movies/episodes get
/// Play/Resume buttons; series get a season selector with an episode list.
struct ItemDetailView: View {
    @Environment(AppEnvironment.self) private var env
    let summary: BaseItemDto
    @State private var model = DetailViewModel()
    @State private var playerItem: PlayerItem?

    private var item: BaseItemDto { model.detail ?? summary }

    var body: some View {
        ScrollView(.vertical, showsIndicators: false) {
            VStack(alignment: .leading, spacing: 40) {
                header

                if summary.kind == .series {
                    seriesSection
                }

                if let error = model.errorMessage {
                    Label(error, systemImage: "exclamationmark.triangle.fill")
                        .foregroundStyle(.red)
                        .padding(.horizontal, Theme.screenPadding)
                }

                Color.clear.frame(height: 40)
            }
        }
        .scrollClipDisabled()
        .background(Theme.bg)
        .ignoresSafeArea(edges: .top)
        .task { await model.load(summary: summary, env: env) }
        .fullScreenCover(item: $playerItem) { item in
            PlayerScreen(item: item, reporter: env.reporter)
        }
    }

    // MARK: - Header (backdrop + metadata + actions)

    private var header: some View {
        ZStack(alignment: .bottomLeading) {
            GeometryReader { geo in
                RemoteImage(url: env.backdropURL(for: item))
                    .frame(width: geo.size.width, height: geo.size.height)
                    .clipped()
            }
            LinearGradient(colors: [.clear, Theme.bg], startPoint: .center, endPoint: .bottom)
            LinearGradient(
                colors: [Theme.bg.opacity(0.9), Theme.bg.opacity(0.4), .clear],
                startPoint: .leading, endPoint: UnitPoint(x: 0.65, y: 0.5)
            )

            VStack(alignment: .leading, spacing: 18) {
                if item.kind == .episode {
                    Text([item.seriesName, item.episodeCode].compactMap { $0 }.joined(separator: " · "))
                        .font(.system(size: 22, weight: .bold))
                        .kerning(2)
                        .foregroundStyle(Theme.accent)
                }
                Text(item.name ?? "—")
                    .font(.system(size: 60, weight: .heavy))
                    .lineLimit(2)
                    .foregroundStyle(Theme.textPrimary)

                HStack(spacing: 18) {
                    if let year = item.productionYear { meta(String(year)) }
                    if let duration = item.durationSeconds { meta(Format.runtime(seconds: duration)) }
                    if let rating = item.communityRating { meta("★ \(String(format: "%.1f", rating))") }
                    if let official = item.officialRating { meta(official) }
                    ForEach(Format.badges(for: item.allMediaStreams), id: \.self) { badge in
                        Text(badge)
                            .font(.system(size: 17, weight: .bold))
                            .foregroundStyle(Theme.textDim)
                            .padding(.horizontal, 12)
                            .padding(.vertical, 4)
                            .overlay(RoundedRectangle(cornerRadius: 7).stroke(Theme.textDim.opacity(0.5), lineWidth: 1))
                    }
                }

                if let genres = item.genres, !genres.isEmpty {
                    Text(genres.prefix(4).joined(separator: " · "))
                        .font(.system(size: 21))
                        .foregroundStyle(Theme.textDim)
                }

                if let overview = item.overview, !overview.isEmpty {
                    Text(overview)
                        .font(.system(size: 24))
                        .foregroundStyle(Theme.textDim)
                        .lineLimit(4)
                        .frame(maxWidth: 980, alignment: .leading)
                }

                if item.kind != .series {
                    actionButtons
                        .padding(.top, 12)
                }
            }
            .padding(.horizontal, Theme.screenPadding)
            .padding(.bottom, 50)
        }
        .frame(height: 700)
    }

    private var actionButtons: some View {
        HStack(spacing: 28) {
            let resumeSeconds = item.resumePositionSeconds
            if resumeSeconds > 1 {
                Button {
                    Task { playerItem = await env.playerItem(for: item, resume: true) }
                } label: {
                    Label("Fortsetzen ab \(Format.clock(seconds: resumeSeconds))", systemImage: "play.fill")
                }
                Button {
                    Task { playerItem = await env.playerItem(for: item, resume: false) }
                } label: {
                    Label("Von vorn", systemImage: "arrow.counterclockwise")
                }
            } else {
                Button {
                    Task { playerItem = await env.playerItem(for: item, resume: false) }
                } label: {
                    Label("Abspielen", systemImage: "play.fill")
                }
            }
        }
    }

    // MARK: - Series: seasons + episodes

    private var seriesSection: some View {
        VStack(alignment: .leading, spacing: 28) {
            if seasonCount > 1 {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 20) {
                        ForEach(model.seasons) { season in
                            Button(season.name ?? "Staffel \(season.indexNumber ?? 0)") {
                                Task {
                                    await model.selectSeason(season.id, seriesId: summary.id, env: env)
                                }
                            }
                            .foregroundStyle(
                                season.id == model.selectedSeasonID ? Theme.accent : Theme.textPrimary
                            )
                        }
                    }
                    .padding(.horizontal, Theme.screenPadding)
                    .padding(.vertical, 16)
                }
                .scrollClipDisabled()
            }

            LazyVStack(alignment: .leading, spacing: 8) {
                ForEach(model.episodes) { episode in
                    EpisodeRow(episode: episode) {
                        Task { playerItem = await env.playerItem(for: episode, resume: episode.resumePositionSeconds > 1) }
                    }
                }
            }
            .padding(.horizontal, Theme.screenPadding - 18)
        }
    }

    private var seasonCount: Int { model.seasons.count }

    private func meta(_ text: String) -> some View {
        Text(text)
            .font(.system(size: 23))
            .foregroundStyle(Theme.textDim)
    }
}
