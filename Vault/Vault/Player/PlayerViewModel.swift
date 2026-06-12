import AVFoundation
import Foundation
import Observation

/// Bridges the PlaybackEngine to SwiftUI: mirrors engine state on the main
/// actor, manages overlay auto-hide and reports progress to Jellyfin.
@Observable
final class PlayerViewModel {
    let item: PlayerItem
    private let engine = PlaybackEngine()
    private let reporter: PlaybackReporter?

    var state: PlayerState = .idle
    var currentSeconds: Double
    var durationSeconds: Double
    var overlayVisible = true

    private var eventTask: Task<Void, Never>?
    private var reportTask: Task<Void, Never>?
    private var overlayHideTask: Task<Void, Never>?
    private var didShutDown = false

    init(item: PlayerItem, reporter: PlaybackReporter?) {
        self.item = item
        self.reporter = reporter
        currentSeconds = item.startSeconds
        durationSeconds = item.durationSeconds ?? 0
    }

    var progress: Double {
        durationSeconds > 0 ? min(1, max(0, currentSeconds / durationSeconds)) : 0
    }

    func attach(layer: AVSampleBufferDisplayLayer) {
        engine.attach(layer: layer)
    }

    @MainActor
    func start() {
        eventTask = Task { [weak self] in
            guard let engine = self?.engine else { return }
            for await event in engine.events {
                guard let self, !Task.isCancelled else { return }
                switch event {
                case .state(let newState):
                    self.state = newState
                    if newState == .playing { self.scheduleOverlayHide() }
                case .time(let seconds):
                    self.currentSeconds = seconds
                case .duration(let seconds):
                    self.durationSeconds = seconds
                }
            }
        }
        engine.open(url: item.streamURL, startAt: item.startSeconds)

        reportTask = Task { [weak self] in
            guard let self else { return }
            await self.reporter?.started(
                itemId: self.item.itemId,
                mediaSourceId: self.item.mediaSourceId,
                positionTicks: JellyfinTicks.from(seconds: self.item.startSeconds)
            )
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(10))
                guard !Task.isCancelled else { return }
                await self.reporter?.progress(
                    itemId: self.item.itemId,
                    mediaSourceId: self.item.mediaSourceId,
                    positionTicks: JellyfinTicks.from(seconds: self.currentSeconds),
                    isPaused: self.state != .playing
                )
            }
        }
        scheduleOverlayHide()
    }

    @MainActor
    func togglePlayPause() {
        engine.togglePlayPause()
        showOverlay()
    }

    @MainActor
    func seek(by delta: Double) {
        engine.seek(by: delta)
        showOverlay()
    }

    @MainActor
    func showOverlay() {
        overlayVisible = true
        scheduleOverlayHide()
    }

    @MainActor
    private func scheduleOverlayHide() {
        overlayHideTask?.cancel()
        overlayHideTask = Task { [weak self] in
            try? await Task.sleep(for: .seconds(4))
            guard let self, !Task.isCancelled, self.state == .playing else { return }
            self.overlayVisible = false
        }
    }

    /// Idempotent — called from both the exit command and onDisappear.
    func shutdown() {
        guard !didShutDown else { return }
        didShutDown = true
        let finalTicks = JellyfinTicks.from(seconds: engine.currentSeconds)
        eventTask?.cancel()
        reportTask?.cancel()
        overlayHideTask?.cancel()
        engine.stop()
        if let reporter {
            let item = self.item
            Task.detached {
                await reporter.stopped(
                    itemId: item.itemId,
                    mediaSourceId: item.mediaSourceId,
                    positionTicks: finalTicks
                )
            }
        }
    }
}
