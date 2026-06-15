import AVFoundation
import Foundation
import Observation

/// Bridges the PlaybackEngine to SwiftUI: mirrors engine state on the main
/// actor, manages overlay auto-hide and reports progress to Jellyfin.
@Observable
final class PlayerViewModel {
    let item: PlayerItem
    private var engine = PlaybackEngine()
    private weak var displayLayer: AVSampleBufferDisplayLayer?
    private let reporter: PlaybackReporter?

    var state: PlayerState = .idle
    var currentSeconds: Double
    var durationSeconds: Double
    var overlayVisible = true
    /// Set when playback runs video-only (unsupported codec, session error, …).
    var audioWarning: String?
    var selectedAudioTrackIndex: Int?

    private var eventTask: Task<Void, Never>?
    private var reportTask: Task<Void, Never>?
    private var overlayHideTask: Task<Void, Never>?
    private var didShutDown = false
    private var didReportStopped = false

    init(item: PlayerItem, reporter: PlaybackReporter?) {
        self.item = item
        self.reporter = reporter
        currentSeconds = item.startSeconds
        durationSeconds = item.durationSeconds ?? 0
        selectedAudioTrackIndex = item.selectedAudioTrackIndex
    }

    var progress: Double {
        durationSeconds > 0 ? min(1, max(0, currentSeconds / durationSeconds)) : 0
    }

    var activeSkipSegment: StreamSegment? {
        item.segments.first { segment in
            segment.end > segment.start
                && currentSeconds >= segment.start
                && currentSeconds < segment.end
        }
    }

    func attach(layer: AVSampleBufferDisplayLayer) {
        displayLayer = layer
        engine.attach(layer: layer)
    }

    @MainActor
    func start() {
        eventTask = Task { [weak self] in
            guard let engine = self?.engine else { return }
            for await event in engine.events {
                guard let self, !Task.isCancelled else { return }
                self.handle(event)
            }
        }
        engine.open(url: item.streamURL, headers: item.httpHeaders, startAt: item.startSeconds, audioStreamIndex: selectedAudioTrackIndex)

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
    private func handle(_ event: PlayerEvent) {
        switch event {
        case .state(let newState):
            state = newState
            switch newState {
            case .playing:
                scheduleOverlayHide()
            case .ended:
                // Close the Jellyfin session now, not when the screen closes —
                // otherwise the server keeps an active session alive while
                // the user sits on the end card.
                overlayVisible = true
                reportStoppedOnce()
            case .failed:
                reportStoppedOnce()
            default:
                break
            }
        case .time(let seconds):
            currentSeconds = seconds
        case .duration(let seconds):
            durationSeconds = seconds
        case .audioUnavailable(let message):
            audioWarning = message
            overlayVisible = true
        }
    }


    @MainActor
    func selectAudioTrack(_ track: AudioTrackInfo) {
        guard selectedAudioTrackIndex != track.index else { return }
        selectedAudioTrackIndex = track.index
        audioWarning = nil
        let resumeAt = currentSeconds
        eventTask?.cancel()
        engine.stop()
        engine = PlaybackEngine()
        if let displayLayer { engine.attach(layer: displayLayer) }
        eventTask = Task { [weak self] in
            guard let engine = self?.engine else { return }
            for await event in engine.events {
                guard let self, !Task.isCancelled else { return }
                self.handle(event)
            }
        }
        engine.open(url: item.streamURL, headers: item.httpHeaders, startAt: resumeAt, audioStreamIndex: track.index)
        showOverlay()
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
    func skipActiveSegment() {
        guard let segment = activeSkipSegment else { return }
        engine.seek(to: segment.end)
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

    /// Ends the playback session on the server exactly once, whether
    /// triggered by .ended, .failed or screen dismissal.
    @MainActor
    private func reportStoppedOnce() {
        guard !didReportStopped else { return }
        didReportStopped = true
        reportTask?.cancel()
        guard let reporter else { return }
        let item = self.item
        let finalTicks = JellyfinTicks.from(seconds: engine.currentSeconds)
        Task.detached {
            await reporter.stopped(
                itemId: item.itemId,
                mediaSourceId: item.mediaSourceId,
                positionTicks: finalTicks
            )
        }
    }

    /// Idempotent — called from both the exit command and onDisappear.
    @MainActor
    func shutdown() {
        guard !didShutDown else { return }
        didShutDown = true
        reportStoppedOnce()
        eventTask?.cancel()
        overlayHideTask?.cancel()
        engine.stop()
    }
}
