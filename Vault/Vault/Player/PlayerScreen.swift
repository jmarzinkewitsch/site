import SwiftUI

/// Full-screen playback. Remote mapping:
/// ◀/▶ (d-pad) → ±10 s, swipe on touch surface → scrub timeline,
/// click/play-pause during scrub → commit scrub and resume,
/// menu during scrub → cancel scrub (stays on screen),
/// menu during normal playback → exit.
struct PlayerScreen: View {
    @Environment(\.dismiss) private var dismiss
    @Environment(AppEnvironment.self) private var env
    @State private var model: PlayerViewModel
    @State private var didDismissPostPlayRating = false
    @State private var isSavingPostPlayRating = false
    @State private var postPlayRatingError: String?
    @State private var nextEpisode: BaseItemDto?
    @State private var nextEpisodePlayerItem: PlayerItem?
    @State private var nextEpisodeCountdown = 10
    @State private var isLoadingNextEpisode = false
    @State private var didCancelNextEpisode = false
    @State private var nextEpisodeTask: Task<Void, Never>?
    @State private var countdownTask: Task<Void, Never>?

    init(item: PlayerItem, reporter: PlaybackReporter?) {
        _model = State(initialValue: PlayerViewModel(item: item, reporter: reporter))
    }

    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()

            VideoLayerView { layer in
                model.attach(layer: layer)
            }
            .id(model.item.id)
            .ignoresSafeArea()

            switch model.state {
            case .opening, .buffering, .seeking:
                ProgressView()
                    .scaleEffect(1.6)
                    .tint(Theme.accent)
            case .failed(let message):
                VStack(spacing: 24) {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .font(.system(size: 60))
                        .foregroundStyle(Theme.accent)
                    Text("Wiedergabe fehlgeschlagen")
                        .font(.system(size: 36, weight: .bold))
                    Text(message)
                        .font(.system(size: 24))
                        .foregroundStyle(Theme.textDim)
                        .multilineTextAlignment(.center)
                        .frame(maxWidth: 1000)
                    Button("Schließen") {
                        model.shutdown()
                        dismiss()
                    }
                }
            default:
                EmptyView()
            }

            // Transparent swipe layer for continuous Siri Remote scrubbing.
            // Not shown when failed or when a modal card is covering the player.
            if !isFailed,
               !shouldShowNextEpisodeCard,
               !shouldShowPostPlayRating,
               !model.isSubtitleSearchPresented,
               model.controlMode == .transport {
                SiriRemoteScrubGesture(
                    onBegin: { model.beginScrub() },
                    onChange: { fraction in model.updateScrub(fraction: fraction) },
                    onEnd: { model.commitScrub() },
                    onCancel: { model.cancelScrub() }
                )
                .ignoresSafeArea()
            }

            if let subtitleText = model.currentSubtitleText, !isFailed {
                SubtitleCaptionView(text: subtitleText, overlayVisible: model.overlayVisible)
                    .transition(.opacity)
            }

            if model.overlayVisible, !isFailed {
                PlayerOverlayView(model: model)
                    .transition(.opacity)
            }

            if !isFailed {
                skipButton
            }

            if let message = model.lastAutoSkipMessage, !isFailed {
                autoSkipToast(message)
            }

            if shouldShowNextEpisodeCard {
                Color.black.opacity(0.45)
                    .ignoresSafeArea()
                NextEpisodeCard(
                    episode: nextEpisode,
                    countdown: nextEpisodeCountdown,
                    isLoading: isLoadingNextEpisode,
                    onPlay: { Task { await playNextEpisode() } },
                    onCancel: { cancelNextEpisode() }
                )
                .transition(.scale.combined(with: .opacity))
            }

            if shouldShowPostPlayRating {
                Color.black.opacity(0.45)
                    .ignoresSafeArea()
                PostPlayRatingView(
                    item: model.item,
                    isSaving: isSavingPostPlayRating,
                    errorMessage: postPlayRatingError,
                    onSave: { snapshot in
                        Task { await savePostPlayRating(snapshot) }
                    },
                    onSkip: {
                        didDismissPostPlayRating = true
                    }
                )
                .transition(.scale.combined(with: .opacity))
            }

            if model.isSubtitleSearchPresented {
                Color.black.opacity(0.45)
                    .ignoresSafeArea()
                SubtitleSearchCard(model: model, onSelect: { subtitle in
                    Task { await downloadSubtitle(subtitle) }
                }, onClose: {
                    model.isSubtitleSearchPresented = false
                })
                .transition(.scale.combined(with: .opacity))
            }
        }
        .animation(Theme.Anim.overlay, value: model.overlayVisible)
        .animation(Theme.Anim.overlay, value: shouldShowPostPlayRating)
        .animation(Theme.Anim.overlay, value: shouldShowNextEpisodeCard)
        .animation(Theme.Anim.overlay, value: model.isSubtitleSearchPresented)
        .animation(Theme.Anim.overlay, value: model.lastAutoSkipMessage)
        .focusable()
        .onPlayPauseCommand {
            if model.isScrubbing {
                model.commitScrub()
            } else {
                model.togglePlayPause()
            }
        }
        .onMoveCommand { direction in
            switch direction {
            case .left where model.controlMode == .transport:
                model.seek(by: -10)
            case .right where model.controlMode == .transport:
                model.seek(by: 10)
            case .down where model.controlMode == .transport:
                model.enterOptions()
            case .up where model.controlMode == .options:
                model.exitOptions()
            default:
                model.showOverlay()
            }
        }
        .onTapGesture { model.showOverlay() }
        .onExitCommand {
            if model.isSubtitleSearchPresented {
                model.isSubtitleSearchPresented = false
            } else if model.closeTrackPanel() {
                // Panel closed; stay in options mode.
            } else if model.controlMode == .options {
                model.exitOptions()
            } else if model.isScrubbing {
                model.cancelScrub()
            } else {
                model.shutdown()
                dismiss()
            }
        }
        .task { model.start() }
        .onChange(of: model.state) { _, state in
            guard case .ended = state else { return }
            handlePlaybackEnded()
        }
        .onChange(of: model.isSubtitleSearchPresented) { _, isPresented in
            if isPresented {
                startSubtitleSearch()
            }
        }
        .onDisappear {
            nextEpisodeTask?.cancel()
            countdownTask?.cancel()
            model.shutdown()
        }
    }

    private var shouldShowNextEpisodeCard: Bool {
        guard !model.item.isTrailer, model.item.type == "Episode", !didCancelNextEpisode else { return false }
        guard case .ended = model.state else { return false }
        return nextEpisode != nil || isLoadingNextEpisode
    }

    @ViewBuilder
    private var skipButton: some View {
        if model.shouldShowSkipButton, let segment = model.activeSkipSegment {
            VStack {
                Spacer()
                HStack {
                    Spacer()
                    Button(segment.title) {
                        model.skipActiveSegment()
                    }
                    .font(.system(size: 28, weight: .bold))
                    .buttonStyle(.borderedProminent)
                    .tint(Theme.accent)
                    .padding(.trailing, Theme.screenPadding)
                    .padding(.bottom, 180)
                }
            }
            .transition(.opacity.combined(with: .move(edge: .trailing)))
        }
    }

    /// Brief non-blocking note shown when an intro/outro was auto-skipped.
    @ViewBuilder
    private func autoSkipToast(_ message: String) -> some View {
        VStack {
            Label(message, systemImage: "forward.fill")
                .font(.system(size: 22, weight: .semibold))
                .foregroundStyle(Theme.textPrimary)
                .padding(.horizontal, 22)
                .padding(.vertical, 12)
                .background(.black.opacity(0.6), in: Capsule())
                .padding(.top, 130)
            Spacer()
        }
        .allowsHitTesting(false)
        .transition(.opacity)
    }

    private var shouldShowPostPlayRating: Bool {
        guard model.item.allowsPostPlayRating, !model.item.isTrailer, !didDismissPostPlayRating else { return false }
        // Episoden werden nicht einzeln bewertet — ganze Serien bewertet man im
        // Detail-Screen. Der Post-Play-Prompt erscheint nur für Filme.
        guard model.item.type != "Episode" else { return false }
        if case .ended = model.state { return true }
        return false
    }

    @MainActor
    private func handlePlaybackEnded() {
        guard !model.item.isTrailer, model.item.type == "Episode" else { return }
        loadNextEpisode()
    }

    @MainActor
    private func loadNextEpisode() {
        guard nextEpisodeTask == nil, !didCancelNextEpisode, let library = env.library else { return }
        isLoadingNextEpisode = true
        nextEpisodeTask = Task { @MainActor in
            defer {
                isLoadingNextEpisode = false
                nextEpisodeTask = nil
            }
            do {
                guard let episode = try await library.nextEpisode(after: model.item.itemId) else { return }
                nextEpisode = episode
                nextEpisodePlayerItem = await env.playerItem(for: episode, resume: false)
                startNextEpisodeCountdown()
            } catch {
                nextEpisode = nil
                nextEpisodePlayerItem = nil
            }
        }
    }

    @MainActor
    private func startNextEpisodeCountdown() {
        countdownTask?.cancel()
        nextEpisodeCountdown = 10
        countdownTask = Task { @MainActor in
            while !Task.isCancelled && nextEpisodeCountdown > 0 {
                try? await Task.sleep(for: .seconds(1))
                guard !Task.isCancelled else { return }
                nextEpisodeCountdown -= 1
            }
            guard !Task.isCancelled else { return }
            await playNextEpisode()
        }
    }

    @MainActor
    private func playNextEpisode() async {
        guard let playerItem = nextEpisodePlayerItem else { return }
        countdownTask?.cancel()
        model.shutdown()
        didDismissPostPlayRating = false
        postPlayRatingError = nil
        nextEpisode = nil
        nextEpisodePlayerItem = nil
        didCancelNextEpisode = false
        nextEpisodeCountdown = 10
        model = PlayerViewModel(item: playerItem, reporter: playerItem.isTrailer ? nil : env.reporter)
        model.start()
    }

    @MainActor
    private func cancelNextEpisode() {
        didCancelNextEpisode = true
        countdownTask?.cancel()
        nextEpisodeTask?.cancel()
        nextEpisode = nil
        nextEpisodePlayerItem = nil
        isLoadingNextEpisode = false
    }

    @MainActor
    private func savePostPlayRating(_ snapshot: VaultRatingSnapshot) async {
        guard let library = env.library else { return }
        isSavingPostPlayRating = true
        defer { isSavingPostPlayRating = false }
        do {
            try await library.saveRatingSnapshot(itemId: model.item.itemId, snapshot: snapshot)
            didDismissPostPlayRating = true
            postPlayRatingError = nil
        } catch {
            postPlayRatingError = "Bewertung konnte nicht gespeichert werden: \(error.localizedDescription)"
        }
    }

    // MARK: - Subtitle search

    @MainActor
    private func startSubtitleSearch() {
        guard let library = env.library else { return }
        model.isSearchingSubtitles = true
        model.subtitleSearchResults = []
        model.subtitleSearchError = nil
        Task { @MainActor in
            do {
                let results = try await library.searchSubtitles(
                    itemId: model.item.itemId,
                    languages: ["ger", "eng"]
                )
                guard model.isSubtitleSearchPresented else { return }
                model.subtitleSearchResults = results
            } catch {
                guard model.isSubtitleSearchPresented else { return }
                model.subtitleSearchError = "Suche fehlgeschlagen: \(error.localizedDescription)"
            }
            model.isSearchingSubtitles = false
        }
    }

    @MainActor
    private func downloadSubtitle(_ result: RemoteSubtitleInfo) async {
        guard let library = env.library else { return }
        model.downloadingSubtitleId = result.id
        defer { model.downloadingSubtitleId = nil }
        do {
            let freshTracks = try await library.downloadSubtitle(
                itemId: model.item.itemId,
                subtitleId: result.id
            )
            // Rewrite docker host in any deliveryURLs — mirrors what
            // AppEnvironment.playerItem does for subtitle tracks.
            let rewritten = freshTracks.map { track -> SubtitleTrackInfo in
                guard let url = track.deliveryURL else { return track }
                return SubtitleTrackInfo(
                    index: track.index,
                    language: track.language,
                    codec: track.codec,
                    displayTitle: track.displayTitle,
                    isExternal: track.isExternal,
                    deliveryURL: env.reachableMediaURL(from: url)
                )
            }
            // Find the newly-added track: prefer an external track whose index
            // wasn't in the old track list.
            let oldIndices = Set(model.subtitleTracks.map(\.index))
            let newIndex = rewritten.first { $0.isExternal && !oldIndices.contains($0.index) }?.index
                ?? rewritten.first { !oldIndices.contains($0.index) }?.index
            model.applyDownloadedSubtitles(rewritten, selectIndex: newIndex)
        } catch {
            model.subtitleSearchError = "Download fehlgeschlagen: \(error.localizedDescription)"
            model.downloadingSubtitleId = nil
        }
    }

    private var isFailed: Bool {
        if case .failed = model.state { return true }
        return false
    }
}


/// Bottom-centered subtitle caption. Lifts above the player chrome when the
/// overlay is visible so the progress bar doesn't overlap it.
private struct SubtitleCaptionView: View {
    let text: String
    let overlayVisible: Bool

    var body: some View {
        VStack {
            Spacer()
            Text(text)
                .font(.system(size: 32, weight: .semibold))
                .foregroundStyle(.white)
                .multilineTextAlignment(.center)
                .shadow(color: .black.opacity(0.85), radius: 2, x: 0, y: 1)
                .padding(.horizontal, 24)
                .padding(.vertical, 12)
                .background(.black.opacity(0.55), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                .padding(.horizontal, Theme.screenPadding * 2)
                .padding(.bottom, overlayVisible ? 220 : 80)
        }
        .allowsHitTesting(false)
    }
}

private struct NextEpisodeCard: View {
    let episode: BaseItemDto?
    let countdown: Int
    let isLoading: Bool
    let onPlay: () -> Void
    let onCancel: () -> Void

    var body: some View {
        VStack(spacing: 22) {
            Text("Nächste Folge")
                .font(.system(size: 42, weight: .bold))

            if let episode {
                Text([episode.episodeCode, episode.name].compactMap { $0 }.joined(separator: " · "))
                    .font(.system(size: 28, weight: .semibold))
                    .multilineTextAlignment(.center)
                Text("Startet automatisch in \(countdown) s")
                    .font(.system(size: 24))
                    .foregroundStyle(Theme.textDim)
            } else if isLoading {
                ProgressView("Nächste Folge wird geladen …")
                    .tint(Theme.accent)
                    .font(.system(size: 24))
            }

            HStack(spacing: 20) {
                Button("Abspielen", action: onPlay)
                    .disabled(episode == nil)
                Button("Abbrechen", action: onCancel)
            }
            .font(.system(size: 24, weight: .semibold))
        }
        .padding(48)
        .frame(maxWidth: 820)
        .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 32, style: .continuous))
    }
}


// MARK: - Subtitle Search Card

private struct SubtitleSearchCard: View {
    let model: PlayerViewModel
    let onSelect: (RemoteSubtitleInfo) -> Void
    let onClose: () -> Void

    var body: some View {
        VStack(spacing: 22) {
            Text("Untertitel online suchen")
                .font(.system(size: 42, weight: .bold))

            if model.isSearchingSubtitles {
                ProgressView("Suche läuft …")
                    .tint(Theme.accent)
                    .font(.system(size: 24))
                    .padding(.vertical, 8)
            } else if model.subtitleSearchResults.isEmpty {
                if let error = model.subtitleSearchError {
                    VStack(spacing: 10) {
                        Image(systemName: "exclamationmark.triangle")
                            .font(.system(size: 36))
                            .foregroundStyle(Theme.accent)
                        Text(error)
                            .font(.system(size: 24))
                            .foregroundStyle(Theme.textDim)
                            .multilineTextAlignment(.center)
                    }
                    .padding(.vertical, 8)
                } else {
                    Text("Keine Untertitel gefunden")
                        .font(.system(size: 24))
                        .foregroundStyle(Theme.textDim)
                        .padding(.vertical, 8)
                }
            } else {
                ScrollView {
                    VStack(spacing: 4) {
                        ForEach(model.subtitleSearchResults) { result in
                            Button {
                                onSelect(result)
                            } label: {
                                HStack {
                                    VStack(alignment: .leading, spacing: 4) {
                                        Text(result.label)
                                            .font(.system(size: 24, weight: .semibold))
                                            .foregroundStyle(Theme.textPrimary)
                                            .lineLimit(2)
                                        if let comment = result.comment, !comment.isEmpty {
                                            Text(comment)
                                                .font(.system(size: 18))
                                                .foregroundStyle(Theme.textDim)
                                                .lineLimit(1)
                                        }
                                    }
                                    Spacer()
                                    if model.downloadingSubtitleId == result.id {
                                        ProgressView()
                                            .tint(Theme.accent)
                                    } else if result.isHashMatch == true {
                                        Image(systemName: "checkmark.seal.fill")
                                            .foregroundStyle(Theme.accent)
                                    }
                                }
                                .padding(.horizontal, 20)
                                .padding(.vertical, 12)
                                .background(Color.white.opacity(0.07), in: RoundedRectangle(cornerRadius: 10))
                            }
                            .disabled(model.downloadingSubtitleId != nil)
                        }
                    }
                    .padding(.horizontal, 4)
                }
                .frame(maxHeight: 420)

                if let error = model.subtitleSearchError {
                    Text(error)
                        .font(.system(size: 20))
                        .foregroundStyle(Theme.accent)
                        .multilineTextAlignment(.center)
                }
            }

            Button("Schließen", action: onClose)
                .font(.system(size: 24, weight: .semibold))
                .disabled(model.downloadingSubtitleId != nil)
        }
        .padding(48)
        .frame(maxWidth: 900)
        .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 32, style: .continuous))
    }
}
