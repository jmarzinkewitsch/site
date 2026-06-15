import SwiftUI

/// Full-screen playback. Remote mapping:
/// play/pause → toggle, click → show overlay, ◀/▶ → ±10 s, menu → exit.
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

            if model.overlayVisible, !isFailed {
                PlayerOverlayView(model: model)
                    .transition(.opacity)
            }

            if !isFailed {
                skipButton
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
        }
        .animation(Theme.Anim.overlay, value: model.overlayVisible)
        .animation(Theme.Anim.overlay, value: shouldShowPostPlayRating)
        .animation(Theme.Anim.overlay, value: shouldShowNextEpisodeCard)
        .focusable()
        .onPlayPauseCommand { model.togglePlayPause() }
        .onMoveCommand { direction in
            switch direction {
            case .left: model.seek(by: -10)
            case .right: model.seek(by: 10)
            default: model.showOverlay()
            }
        }
        .onTapGesture { model.showOverlay() }
        .onExitCommand {
            model.shutdown()
            dismiss()
        }
        .task { model.start() }
        .onChange(of: model.state) { _, state in
            guard case .ended = state else { return }
            handlePlaybackEnded()
        }
        .onDisappear {
            nextEpisodeTask?.cancel()
            countdownTask?.cancel()
            model.shutdown()
        }
    }

    private var shouldShowNextEpisodeCard: Bool {
        guard model.item.type == "Episode", !didCancelNextEpisode else { return false }
        guard case .ended = model.state else { return false }
        return nextEpisode != nil || isLoadingNextEpisode
    }

    @ViewBuilder
    private var skipButton: some View {
        if let segment = model.activeSkipSegment {
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

    private var shouldShowPostPlayRating: Bool {
        guard !didDismissPostPlayRating else { return false }
        // Episoden werden nicht einzeln bewertet — ganze Serien bewertet man im
        // Detail-Screen. Der Post-Play-Prompt erscheint nur für Filme.
        guard model.item.type != "Episode" else { return false }
        if case .ended = model.state { return true }
        return false
    }

    @MainActor
    private func handlePlaybackEnded() {
        guard model.item.type == "Episode" else { return }
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
        model = PlayerViewModel(item: playerItem, reporter: env.reporter)
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

    private var isFailed: Bool {
        if case .failed = model.state { return true }
        return false
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
