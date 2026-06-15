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

    init(item: PlayerItem, reporter: PlaybackReporter?) {
        _model = State(initialValue: PlayerViewModel(item: item, reporter: reporter))
    }

    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()

            VideoLayerView { layer in
                model.attach(layer: layer)
            }
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
        .onDisappear { model.shutdown() }
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
