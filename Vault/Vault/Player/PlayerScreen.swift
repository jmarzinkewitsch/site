import SwiftUI

/// Full-screen playback. Remote mapping:
/// play/pause → toggle, click → show overlay, ◀/▶ → ±10 s, menu → exit.
struct PlayerScreen: View {
    @Environment(\.dismiss) private var dismiss
    @State private var model: PlayerViewModel

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
        }
        .animation(Theme.Anim.overlay, value: model.overlayVisible)
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

    private var isFailed: Bool {
        if case .failed = model.state { return true }
        return false
    }
}
