import AVFoundation
import CoreGraphics
import Foundation
import Observation

/// Bridges the PlaybackEngine to SwiftUI: mirrors engine state on the main
/// actor, manages overlay auto-hide and reports progress to Jellyfin.
@Observable
final class PlayerViewModel {
    enum ControlMode: Equatable {
        case transport
        case options
    }

    enum TrackPanel: Equatable {
        case audio
        case subtitles
    }

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
    var selectedSubtitleTrackIndex: Int?
    var currentSubtitleText: String?
    var controlMode: ControlMode = .transport
    var openTrackPanel: TrackPanel?

    // MARK: - Dynamic subtitle track list (may grow after online download)
    var subtitleTracks: [SubtitleTrackInfo] = []

    // MARK: - Online subtitle search state
    var isSubtitleSearchPresented: Bool = false
    var isSearchingSubtitles: Bool = false
    var subtitleSearchResults: [RemoteSubtitleInfo] = []
    var subtitleSearchError: String? = nil
    var downloadingSubtitleId: String? = nil

    // MARK: - Scrub state (observable)
    var isScrubbing: Bool = false
    var scrubTargetSeconds: Double = 0
    var scrubPreviewImage: CGImage? = nil

    /// Transient note shown briefly after an automatic intro/outro skip.
    var lastAutoSkipMessage: String?

    private var eventTask: Task<Void, Never>?
    private var reportTask: Task<Void, Never>?
    private var overlayHideTask: Task<Void, Never>?
    private var previewTask: Task<Void, Never>?
    private var subtitleLoadTask: Task<Void, Never>?
    private var scrubBaseSeconds: Double = 0
    private var lastPreviewLoadSeconds: Double = -9999
    private var didShutDown = false
    private var didReportStopped = false

    /// Segments already auto-skipped once, so rewinding into them won't re-skip.
    private var autoSkippedSegments: Set<StreamSegment> = []
    private var autoSkipMessageTask: Task<Void, Never>?

    // Auto-mark-as-watched: fire once per PlayerViewModel instance when the
    // viewer is within autoWatchedLeadSeconds of the end.
    private let autoWatchedLeadSeconds: Double = 180
    private var didAutoMarkWatched = false

    private let trickplayProvider: TrickplayImageProvider?

    init(item: PlayerItem, reporter: PlaybackReporter?) {
        self.item = item
        self.reporter = reporter
        if let info = item.trickplay {
            trickplayProvider = TrickplayImageProvider(info: info, headers: item.httpHeaders)
        } else {
            trickplayProvider = nil
        }
        currentSeconds = item.startSeconds
        durationSeconds = item.durationSeconds ?? 0
        selectedAudioTrackIndex = item.selectedAudioTrackIndex
        selectedSubtitleTrackIndex = item.selectedSubtitleTrackIndex
        subtitleTracks = item.subtitleTracks
    }

    var progress: Double {
        durationSeconds > 0 ? min(1, max(0, currentSeconds / durationSeconds)) : 0
    }

    var showsAudioControl: Bool {
        item.audioTracks.count > 1
    }

    var showsSubtitleControl: Bool {
        !item.isTrailer
    }

    var hasTrackControls: Bool {
        showsAudioControl || showsSubtitleControl
    }

    var activeSkipSegment: StreamSegment? {
        item.segments.first { segment in
            segment.end > segment.start
                && currentSeconds >= segment.start
                && currentSeconds < segment.end
        }
    }

    /// Settings toggle ("autoSkipSegments"); defaults on when never set.
    private var autoSkipEnabled: Bool {
        UserDefaults.standard.object(forKey: "autoSkipSegments") as? Bool ?? true
    }

    /// Manual skip button: always shown when auto-skip is off; with auto-skip on,
    /// only for a segment we already auto-skipped (i.e. the user rewound into it).
    var shouldShowSkipButton: Bool {
        guard let segment = activeSkipSegment else { return false }
        if !autoSkipEnabled { return true }
        return autoSkippedSegments.contains(segment)
    }

    /// Auto-skips the active intro/outro once, on the playback progress tick.
    @MainActor
    private func maybeAutoSkip() {
        guard autoSkipEnabled, !isScrubbing,
              let segment = activeSkipSegment,
              !autoSkippedSegments.contains(segment) else { return }
        autoSkippedSegments.insert(segment)
        engine.seek(to: segment.end)
        lastAutoSkipMessage = segment.type == "outro" ? "Abspann übersprungen" : "Intro übersprungen"
        autoSkipMessageTask?.cancel()
        autoSkipMessageTask = Task { [weak self] in
            try? await Task.sleep(for: .seconds(1.8))
            guard let self, !Task.isCancelled else { return }
            self.lastAutoSkipMessage = nil
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
        engine.open(
            url: item.streamURL,
            headers: item.httpHeaders,
            startAt: item.startSeconds,
            audioStreamIndex: selectedAudioTrackIndex,
            subtitleStreamIndex: selectedSubtitleTrackIndex
        )

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
                // Check whether we have reached the auto-watched threshold.
                self.reportAutoWatchedIfNeeded()
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
                if isScrubbing { cancelScrub() }
                // Close the Jellyfin session now, not when the screen closes —
                // otherwise the server keeps an active session alive while
                // the user sits on the end card.
                overlayVisible = true
                // If somehow the periodic check didn't fire (e.g. the content
                // ended abruptly), mark watched at the boundary itself.
                reportAutoWatchedIfNeeded()
                reportStoppedOnce()
            case .failed:
                reportStoppedOnce()
            default:
                break
            }
        case .time(let seconds):
            currentSeconds = seconds
            maybeAutoSkip()
        case .duration(let seconds):
            durationSeconds = seconds
        case .audioUnavailable(let message):
            audioWarning = message
            overlayVisible = true
        case .subtitle(let text):
            currentSubtitleText = text
        }
    }


    @MainActor
    func selectAudioTrack(_ track: AudioTrackInfo) {
        guard selectedAudioTrackIndex != track.index else { return }
        if isScrubbing { cancelScrub() }
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
        engine.open(
            url: item.streamURL,
            headers: item.httpHeaders,
            startAt: resumeAt,
            audioStreamIndex: track.index,
            subtitleStreamIndex: selectedSubtitleTrackIndex
        )
        reloadExternalSubtitleIfNeeded()
        showOverlay()
    }

    /// The embedded-subtitle index handed to `engine.open` matches nothing in
    /// the container for an external track, so a freshly-rebuilt engine (after
    /// an audio switch) would drop the sidecar. Re-download it into the store.
    @MainActor
    private func reloadExternalSubtitleIfNeeded() {
        guard let index = selectedSubtitleTrackIndex,
              let track = subtitleTracks.first(where: { $0.index == index }),
              track.isExternal, let url = track.deliveryURL else { return }
        let headers = item.httpHeaders
        subtitleLoadTask?.cancel()
        subtitleLoadTask = Task { [weak self] in
            let cues = await ExternalSubtitleLoader.load(from: url, headers: headers)
            guard let self, !Task.isCancelled,
                  self.selectedSubtitleTrackIndex == index else { return }
            self.engine.setExternalCues(cues)
        }
    }

    @MainActor
    func selectSubtitleTrack(_ track: SubtitleTrackInfo?) {
        guard selectedSubtitleTrackIndex != track?.index else { return }
        selectedSubtitleTrackIndex = track?.index
        currentSubtitleText = nil
        subtitleLoadTask?.cancel()
        subtitleLoadTask = nil

        if let track, track.isExternal, let url = track.deliveryURL {
            // External sub isn't in the container — clear any embedded decoder,
            // then download and parse the sidecar before handing cues over.
            engine.selectSubtitleStream(index: nil)
            let headers = item.httpHeaders
            subtitleLoadTask = Task { [weak self] in
                let cues = await ExternalSubtitleLoader.load(from: url, headers: headers)
                guard let self, !Task.isCancelled,
                      self.selectedSubtitleTrackIndex == track.index else { return }
                self.engine.setExternalCues(cues)
            }
        } else {
            engine.selectSubtitleStream(index: track?.index)
        }
        showOverlay()
    }

    @MainActor
    func enterOptions() {
        guard hasTrackControls else { return }
        if isScrubbing { cancelScrub() }
        overlayVisible = true
        controlMode = .options
        overlayHideTask?.cancel()
    }

    @MainActor
    func exitOptions() {
        openTrackPanel = nil
        guard controlMode == .options else { return }
        controlMode = .transport
        scheduleOverlayHide()
    }

    @MainActor
    func showTrackPanel(_ panel: TrackPanel) {
        guard controlMode == .options else { return }
        openTrackPanel = panel
        overlayVisible = true
        overlayHideTask?.cancel()
    }

    @MainActor
    @discardableResult
    func closeTrackPanel() -> Bool {
        guard openTrackPanel != nil else { return false }
        openTrackPanel = nil
        return true
    }

    @MainActor
    func togglePlayPause() {
        engine.togglePlayPause()
        showOverlay()
    }

    @MainActor
    func seek(by delta: Double) {
        if isScrubbing { cancelScrub() }
        engine.seek(by: delta)
        showOverlay()
    }

    @MainActor
    func skipActiveSegment() {
        guard let segment = activeSkipSegment else { return }
        if isScrubbing { cancelScrub() }
        engine.seek(to: segment.end)
        showOverlay()
    }

    // MARK: - Scrubbing

    /// Called when the user starts a swipe on the Siri Remote touch surface.
    /// The engine is paused immediately; only a virtual playhead moves during
    /// the drag. The real seek happens once on `commitScrub()`.
    @MainActor
    func beginScrub() {
        guard !isScrubbing else { return }
        isScrubbing = true
        scrubBaseSeconds = currentSeconds
        scrubTargetSeconds = currentSeconds
        lastPreviewLoadSeconds = -9999
        engine.pause()
        showOverlay()
        loadPreview(for: currentSeconds)
    }

    /// Called continuously by `SiriRemoteScrubGesture` with the cumulative
    /// horizontal translation expressed as a fraction of the touch-surface
    /// width (positive = forward, negative = backward).
    @MainActor
    func updateScrub(fraction: Double) {
        guard isScrubbing, durationSeconds > 0 else { return }
        let upper = max(0, durationSeconds - 1)
        let target = min(upper, max(0, scrubBaseSeconds + fraction * durationSeconds))
        scrubTargetSeconds = target

        // Throttle thumbnail requests: only reload when the virtual playhead
        // has moved more than 2 s since the last request.
        if abs(target - lastPreviewLoadSeconds) > 2 {
            loadPreview(for: target)
        }
    }

    /// Commits the scrub: seeks the engine to the chosen position and resumes.
    @MainActor
    func commitScrub() {
        guard isScrubbing else { return }
        let target = scrubTargetSeconds
        isScrubbing = false
        scrubPreviewImage = nil
        previewTask?.cancel()
        previewTask = nil
        engine.seek(to: target)
        engine.play()
        scheduleOverlayHide()
    }

    /// Cancels the scrub without moving the playhead; playback resumes at the
    /// position where scrubbing began.
    @MainActor
    func cancelScrub() {
        guard isScrubbing else { return }
        isScrubbing = false
        scrubPreviewImage = nil
        previewTask?.cancel()
        previewTask = nil
        engine.play()
        scheduleOverlayHide()
    }

    /// Debounce-loads a trickplay thumbnail for `seconds` and assigns it to
    /// `scrubPreviewImage` on the main actor once available.
    @MainActor
    private func loadPreview(for seconds: Double) {
        lastPreviewLoadSeconds = seconds
        previewTask?.cancel()
        guard let provider = trickplayProvider else { return }
        let capturedTarget = seconds
        previewTask = Task { [weak self] in
            let image = await provider.image(atSeconds: capturedTarget)
            guard let self, !Task.isCancelled, self.isScrubbing else { return }
            self.scrubPreviewImage = image
        }
    }

    @MainActor
    func showOverlay() {
        overlayVisible = true
        scheduleOverlayHide()
    }

    @MainActor
    private func scheduleOverlayHide() {
        // Keep overlay visible while the user is scrubbing or navigating track controls.
        guard !isScrubbing, controlMode == .transport else { return }
        overlayHideTask?.cancel()
        overlayHideTask = Task { [weak self] in
            try? await Task.sleep(for: .seconds(4))
            guard let self,
                  !Task.isCancelled,
                  self.state == .playing,
                  !self.isScrubbing,
                  self.controlMode == .transport else { return }
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

    // MARK: - Auto-watched

    /// Marks the item as watched on the server when the viewer has reached the
    /// last `autoWatchedLeadSeconds` of the runtime. Fires at most once per
    /// PlayerViewModel instance so rapid progress ticks don't produce duplicates.
    /// Trailers are excluded — they share the same pipeline but should never
    /// affect the library watched state.
    @MainActor
    private func reportAutoWatchedIfNeeded() {
        guard !didAutoMarkWatched,
              !item.isTrailer,
              durationSeconds > autoWatchedLeadSeconds,
              currentSeconds >= durationSeconds - autoWatchedLeadSeconds else { return }
        didAutoMarkWatched = true
        guard let reporter else { return }
        let itemId = item.itemId
        Task.detached {
            await reporter.markWatched(itemId: itemId)
        }
    }

    // MARK: - Online subtitle search actions

    @MainActor
    func presentSubtitleSearch() {
        openTrackPanel = nil
        isSubtitleSearchPresented = true
    }

    /// Called by PlayerScreen after a successful subtitle download.
    /// Replaces the in-memory track list and optionally selects the new track
    /// so the existing external-subtitle pipeline picks it up immediately.
    @MainActor
    func applyDownloadedSubtitles(_ tracks: [SubtitleTrackInfo], selectIndex: Int?) {
        subtitleTracks = tracks
        if let idx = selectIndex {
            let track = tracks.first { $0.index == idx }
            selectSubtitleTrack(track)
        }
        // Dismiss the search sheet and reset search state.
        isSubtitleSearchPresented = false
        isSearchingSubtitles = false
        subtitleSearchResults = []
        subtitleSearchError = nil
        downloadingSubtitleId = nil
    }

    /// Idempotent — called from both the exit command and onDisappear.
    @MainActor
    func shutdown() {
        guard !didShutDown else { return }
        didShutDown = true
        reportStoppedOnce()
        eventTask?.cancel()
        overlayHideTask?.cancel()
        previewTask?.cancel()
        subtitleLoadTask?.cancel()
        engine.stop()
    }
}
