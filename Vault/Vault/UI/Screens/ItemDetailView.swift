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
                    StatusView(kind: .error(error))
                        .padding(.horizontal, Theme.screenPadding)
                } else if model.isLoading {
                    StatusView(kind: .loading("Lädt …"))
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
                    .accessibilityHidden(true)
            }
            LinearGradient(colors: [.clear, Theme.bg], startPoint: .center, endPoint: .bottom)
            LinearGradient(
                colors: [Theme.bg.opacity(Theme.Opacity.scrimHeader), Theme.bg.opacity(Theme.Opacity.scrimHeaderMid), .clear],
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
                    if let official = item.officialRating { meta(official) }
                    BadgeRow(badges: Format.badges(for: item.allMediaStreams))
                }

                scoreBadges

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
                    VStack(alignment: .leading, spacing: 18) {
                        actionButtons
                        ratingInput
                    }
                    .padding(.top, 12)
                }
            }
            .padding(.horizontal, Theme.screenPadding)
            .padding(.bottom, 50)
        }
        .frame(height: Theme.detailHeaderHeight)
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

    private var scoreBadges: some View {
        HStack(spacing: 12) {
            if let imdb = item.externalScores?.imdb ?? item.communityRating {
                scoreBadge(label: "IMDb", value: String(format: "%.1f", imdb))
            }
            if let rt = item.externalScores?.rottenTomatoes ?? item.criticRating.map({ Int($0) }) {
                scoreBadge(label: "RT", value: "\(rt)%")
            }
            if let metacritic = item.externalScores?.metacritic {
                scoreBadge(label: "Metacritic", value: "\(metacritic)")
            }
            if let own = item.userRating {
                scoreBadge(label: "Deine Wertung", value: String(format: "%.1f", own))
            }
        }
        .frame(height: 34)
    }

    private func scoreBadge(label: String, value: String) -> some View {
        HStack(spacing: 6) {
            Text(label)
                .foregroundStyle(Theme.textDim)
            Text(value)
                .foregroundStyle(Theme.textPrimary)
        }
        .font(.system(size: 18, weight: .bold))
        .padding(.horizontal, 12)
        .padding(.vertical, 7)
        .background(Theme.bg.opacity(0.55), in: Capsule())
        .overlay(Capsule().stroke(Theme.textDim.opacity(0.35), lineWidth: 1))
    }

    private var ratingInput: some View {
        HStack(spacing: 14) {
            Text("Deine Bewertung")
                .font(.system(size: 21, weight: .bold))
                .foregroundStyle(Theme.textPrimary)
            HStack(spacing: 4) {
                ForEach(1...5, id: \.self) { star in
                    Button {
                        Task { await model.setRating(Double(star * 2), itemId: item.id, env: env) }
                    } label: {
                        Image(systemName: star <= selectedStarCount ? "star.fill" : "star")
                            .font(.system(size: 28, weight: .bold))
                            .foregroundStyle(star <= selectedStarCount ? Theme.accent : Theme.textDim)
                    }
                    .buttonStyle(.plain)
                    .disabled(model.isSavingRating)
                    .accessibilityLabel("\(star) von 5 Sternen")
                }
            }
            if model.isSavingRating {
                ProgressView().controlSize(.small)
            } else if let message = model.ratingMessage {
                Text(message)
                    .font(.system(size: 17, weight: .semibold))
                    .foregroundStyle(Theme.textDim)
            }
        }
    }

    private var selectedStarCount: Int {
        guard let rating = item.userRating else { return 0 }
        return max(0, min(5, Int((rating / 2).rounded())))
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
