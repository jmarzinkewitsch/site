import SwiftUI

/// Detail screen for movies, series and episodes. Movies/episodes get
/// Play/Resume buttons; series get a season selector with an episode list.
struct ItemDetailView: View {
    @Environment(AppEnvironment.self) private var env
    let summary: BaseItemDto
    @State private var model = DetailViewModel()
    @State private var playerItem: PlayerItem?
    @State private var resumePromptEpisode: BaseItemDto?
    @State private var isLoadingTrailer = false
    @State private var trailerErrorMessage: String?
    @State private var isShowingDetailedRating = false
    @Namespace private var episodeFocusScope

    private var item: BaseItemDto { model.detail ?? summary }

    /// The series whose seasons/episodes we browse: the item itself for a series,
    /// or the parent series when a single episode was opened.
    private var seriesID: String {
        summary.kind == .series ? summary.id : (summary.seriesId ?? summary.id)
    }

    /// When a single episode was opened, the episode to highlight + jump to.
    private var highlightedEpisodeID: String? {
        summary.kind == .episode ? summary.id : nil
    }

    var body: some View {
        ScrollView(.vertical, showsIndicators: false) {
            VStack(alignment: .leading, spacing: 40) {
                header

                if summary.kind == .series || summary.kind == .episode {
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
        .ignoresSafeArea()
        .task { await model.load(summary: summary, env: env) }
        .fullScreenCover(item: $playerItem, onDismiss: {
            Task { await model.refreshPlaybackState(summary: summary, env: env) }
        }) { item in
            PlayerScreen(item: item, reporter: item.isTrailer ? nil : env.reporter)
        }
        .sheet(isPresented: $isShowingDetailedRating) {
            DetailedRatingView(
                item: item,
                isWatched: displayedIsPlayed,
                isSaving: model.isSavingDetailedRating,
                errorMessage: model.detailedRatingErrorMessage,
                onSave: { snapshot, markWatched in
                    Task {
                        await model.saveDetailedRating(snapshot, item: item, markWatched: markWatched, env: env)
                        if model.detailedRatingErrorMessage == nil {
                            isShowingDetailedRating = false
                        }
                    }
                },
                onCancel: {
                    isShowingDetailedRating = false
                }
            )
            .presentationDetents([.large])
        }
        .confirmationDialog(
            "Wiedergabe fortsetzen?",
            isPresented: resumePromptBinding,
            titleVisibility: .visible,
            presenting: resumePromptEpisode
        ) { episode in
            Button("Fortsetzen ab \(Format.clock(seconds: episode.resumePositionSeconds))") {
                Task { await play(episode, resume: true) }
            }
            Button("Von vorn") {
                Task { await play(episode, resume: false) }
            }
        } message: { episode in
            Text([episode.episodeCode, episode.name].compactMap { $0 }.joined(separator: " · "))
        }
    }

    // MARK: - Header (backdrop + metadata + actions)

    private var header: some View {
        ZStack(alignment: .bottomLeading) {
            GeometryReader { geo in
                RemoteImage(url: headerBackdropURL)
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
                    Task { await play(item, resume: false) }
                } label: {
                    Label("Abspielen", systemImage: "play.fill")
                }
            }
            if item.trailerUrl != nil {
                Button {
                    Task { await playTrailer() }
                } label: {
                    Label(isLoadingTrailer ? "Trailer lädt …" : "Trailer", systemImage: "film.fill")
                }
                .disabled(isLoadingTrailer)
            }
            Button {
                Task { await model.setWatched(!displayedIsPlayed, itemId: item.id, env: env) }
            } label: {
                Label(
                    displayedIsPlayed ? "Als ungesehen markieren" : "Als gesehen markieren",
                    systemImage: displayedIsPlayed ? "checkmark.circle.fill" : "circle"
                )
            }
            .disabled(model.isSavingWatched)
            Button {
                isShowingDetailedRating = true
            } label: {
                Label("Detailliert bewerten", systemImage: "slider.horizontal.3")
            }
            .disabled(model.isSavingDetailedRating)
        }
        .overlay(alignment: .bottomLeading) {
            if let trailerErrorMessage {
                Text(trailerErrorMessage)
                    .font(.system(size: 17, weight: .semibold))
                    .foregroundStyle(Theme.textDim)
                    .padding(.top, 72)
            }
        }
    }

    @MainActor
    private func play(_ item: BaseItemDto, resume: Bool) async {
        resumePromptEpisode = nil
        playerItem = await env.playerItem(for: item, resume: resume)
    }

    @MainActor
    private func playTrailer() async {
        isLoadingTrailer = true
        trailerErrorMessage = nil
        defer { isLoadingTrailer = false }
        if let trailer = await env.trailerPlayerItem(for: item) {
            playerItem = trailer
        } else {
            trailerErrorMessage = env.playbackError ?? "Trailer ist momentan nicht verfügbar."
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
            if model.isSavingWatched {
                ProgressView().controlSize(.small)
            } else if let message = model.watchedMessage {
                Text(message)
                    .font(.system(size: 17, weight: .semibold))
                    .foregroundStyle(Theme.textDim)
            }
            if model.isSavingDetailedRating {
                ProgressView().controlSize(.small)
            } else if let message = model.detailedRatingMessage {
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

    private var displayedIsPlayed: Bool {
        model.watchedOverrides[item.id] ?? item.isPlayed
    }

    private var headerBackdropURL: URL? {
        if let raw = model.headerBackdropURL {
            return env.reachableMediaURL(from: raw)
        }
        return env.backdropURL(for: item)
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
                                    await model.selectSeason(season.id, seriesId: seriesID, env: env)
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
                    EpisodeRow(
                        episode: episode,
                        watchedOverride: model.watchedOverrides[episode.id],
                        isHighlighted: episode.id == highlightedEpisodeID,
                        toggleWatched: {
                            Task {
                                await model.setEpisodeWatched(
                                    !(model.watchedOverrides[episode.id] ?? episode.isPlayed),
                                    episode: episode,
                                    env: env
                                )
                            }
                        }
                    ) {
                        if episode.resumePositionSeconds > 1 {
                            resumePromptEpisode = episode
                        } else {
                            Task { await play(episode, resume: false) }
                        }
                    }
                    .id(episode.id)
                    // Pressing down from the hero lands on the opened episode.
                    .prefersDefaultFocus(episode.id == highlightedEpisodeID, in: episodeFocusScope)
                }
            }
            .padding(.horizontal, Theme.screenPadding - 18)
            .focusScope(episodeFocusScope)
        }
    }

    private var seasonCount: Int { model.seasons.count }

    private var resumePromptBinding: Binding<Bool> {
        Binding {
            resumePromptEpisode != nil
        } set: { isPresented in
            if !isPresented {
                resumePromptEpisode = nil
            }
        }
    }

    private func meta(_ text: String) -> some View {
        Text(text)
            .font(.system(size: 23))
            .foregroundStyle(Theme.textDim)
    }
}

private struct DetailedRatingView: View {
    let item: BaseItemDto
    let isWatched: Bool
    let isSaving: Bool
    let errorMessage: String?
    let onSave: (VaultRatingSnapshot, Bool) -> Void
    let onCancel: () -> Void

    @State private var jannoRating = 0
    @State private var tannoRating = 0
    @State private var fearFactor = 0.0
    @State private var markWatched = true

    var body: some View {
        VStack(alignment: .leading, spacing: 28) {
            VStack(alignment: .leading, spacing: 8) {
                Text("Detaillierte Bewertung")
                    .font(.system(size: 44, weight: .heavy))
                    .foregroundStyle(Theme.textPrimary)
                Text(item.name ?? "—")
                    .font(.system(size: 24, weight: .semibold))
                    .foregroundStyle(Theme.textDim)
            }

            ratingRow(title: "Janno", value: $jannoRating)
            ratingRow(title: "Tanno", value: $tannoRating)
            fearFactorInput

            Toggle("Als gesehen markieren", isOn: $markWatched)
                .font(.system(size: 22, weight: .bold))
                .foregroundStyle(Theme.textPrimary)
                .disabled(isWatched)

            if let errorMessage {
                Text(errorMessage)
                    .font(.system(size: 18, weight: .semibold))
                    .foregroundStyle(.red)
            }

            HStack(spacing: 20) {
                Button {
                    onSave(snapshot, markWatched && !isWatched)
                } label: {
                    if isSaving {
                        Label("Speichert …", systemImage: "hourglass")
                    } else {
                        Label("Bewertung speichern", systemImage: "checkmark.circle.fill")
                    }
                }
                .disabled(isSaving || !hasRating)

                Button("Abbrechen") { onCancel() }
                    .disabled(isSaving)
            }
        }
        .padding(46)
        .frame(maxWidth: 840, alignment: .leading)
        .background(Theme.bg)
        .onAppear {
            markWatched = !isWatched
        }
    }

    private var hasRating: Bool {
        jannoRating > 0 || tannoRating > 0 || fearFactor > 0
    }

    private var snapshot: VaultRatingSnapshot {
        VaultRatingSnapshot(
            title: item.name ?? "—",
            type: item.type ?? "Movie",
            year: item.productionYear,
            tmdbId: item.tmdbId,
            imdbId: item.imdbId,
            jannoRating: jannoRating > 0 ? Double(jannoRating * 2) : nil,
            tannoRating: tannoRating > 0 ? Double(tannoRating * 2) : nil,
            tannoFearFactor: fearFactor > 0 ? fearFactor : nil
        )
    }

    private var fearFactorInput: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Label("Gruselfaktor", systemImage: "moon.stars.fill")
                Spacer()
                Text("\(Int(fearFactor))/20")
            }
            .font(.system(size: 22, weight: .bold))
            .foregroundStyle(Theme.textPrimary)

            HStack(spacing: 18) {
                Button {
                    fearFactor = max(0, fearFactor - 1)
                } label: {
                    Image(systemName: "minus.circle.fill")
                        .font(.system(size: 34, weight: .bold))
                }
                .disabled(fearFactor <= 0)

                GeometryReader { proxy in
                    ZStack(alignment: .leading) {
                        Capsule()
                            .fill(Theme.textDim.opacity(0.25))
                        Capsule()
                            .fill(Theme.accent)
                            .frame(width: proxy.size.width * (fearFactor / 20))
                    }
                }
                .frame(height: 18)
                .accessibilityLabel("Gruselfaktor")
                .accessibilityValue("\(Int(fearFactor)) von 20")

                Button {
                    fearFactor = min(20, fearFactor + 1)
                } label: {
                    Image(systemName: "plus.circle.fill")
                        .font(.system(size: 34, weight: .bold))
                }
                .disabled(fearFactor >= 20)
            }
            .buttonStyle(.plain)
        }
    }

    private func ratingRow(title: String, value: Binding<Int>) -> some View {
        HStack(spacing: 18) {
            Text(title)
                .font(.system(size: 24, weight: .bold))
                .foregroundStyle(Theme.textPrimary)
                .frame(width: 170, alignment: .leading)
            HStack(spacing: 8) {
                ForEach(1...5, id: \.self) { star in
                    Button {
                        value.wrappedValue = star
                    } label: {
                        Image(systemName: star <= value.wrappedValue ? "star.fill" : "star")
                            .font(.system(size: 32, weight: .bold))
                            .foregroundStyle(star <= value.wrappedValue ? Theme.accent : Theme.textDim)
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel("\(title): \(star) von 5 Sternen")
                }
            }
        }
    }
}
