import AVFoundation
import CoreMedia
import Foundation
import Libavcodec
import Libavformat
import Libavutil

enum PlayerState: Equatable {
    case idle
    case opening
    case buffering
    case playing
    case paused
    case seeking
    case ended
    case failed(String)
}

enum PlayerEvent {
    case state(PlayerState)
    case time(Double)
    case duration(Double)
    /// Playback continues video-only; the message says why.
    case audioUnavailable(String)
}

/// Orchestrates demuxing, video sample feeding, audio decoding and A/V sync.
///
/// Threads:
/// - engine queue (serial): state machine, open/seek/play/pause, sync timer
/// - demux thread: av_read_frame loop + av_seek_frame (sole owner of all
///   libavformat calls after open)
/// - audio thread: packet → PCM → ring buffer (sole owner of the audio codec)
/// - video feed queue (in VideoRenderer): packet → CMSampleBuffer → layer
/// - audio render callback (in AudioRenderer): ring buffer → speaker, clock
///
/// Clocking: audio is master. Video runs off the display layer's CMTimebase,
/// which the sync timer slaves to the audio clock.
///
/// Seeking: `seek(to:)` bumps `generation` and parks a request. The demux
/// thread seeks, flushes both queues, hands off to `finishSeek` on the engine
/// queue (which resets ring/clock/layer) and only resumes reading after
/// `seekResume` is signalled — so no new-generation packet can race the
/// reset. Consumers drop any popped packet whose generation tag is stale.
final class PlaybackEngine {
    let events: AsyncStream<PlayerEvent>
    private let eventSink: AsyncStream<PlayerEvent>.Continuation

    private let queue = DispatchQueue(label: "vault.player.engine")
    private let demuxer = Demuxer()
    private let videoQueue = PacketQueue(maxBytes: 40 << 20)
    private let audioQueue = PacketQueue(maxBytes: 8 << 20)
    private let videoRenderer = VideoRenderer()
    private var videoFactory: VideoSampleFactory?
    private var audioDecoder: AudioDecoder?
    private var audioRing: PCMRingBuffer?
    private var audioRenderer: AudioRenderer?

    private var state: PlayerState = .idle {
        didSet { if state != oldValue { eventSink.yield(.state(state)) } }
    }
    private var durationSeconds: Double = 0
    private var wantsPlay = true
    private var audioEngineRunning = false
    private var audioStartFailed = false
    private var syncTimer: DispatchSourceTimer?

    private let closed = AtomicValue(false)
    private let reachedEOF = AtomicValue(false)
    private let waitingForKeyframe = AtomicValue(true)
    private let pendingSeek = AtomicValue<(target: Double, generation: Int)?>(nil)
    private let generation = AtomicValue(0)

    // Lifecycle handshakes (see stop() / demuxLoop)
    private let demuxDone = DispatchSemaphore(value: 0)
    private let audioDone = DispatchSemaphore(value: 0)
    private let seekResume = DispatchSemaphore(value: 0)
    private var demuxStarted = false   // engine queue only
    private var audioStarted = false   // engine queue only

    init() {
        (events, eventSink) = AsyncStream.makeStream(of: PlayerEvent.self)
    }

    // MARK: - Public API

    /// Main thread: wire up the display layer before/while opening.
    func attach(layer: AVSampleBufferDisplayLayer) {
        try? videoRenderer.attach(layer: layer)
    }

    func open(url: URL, headers: [String: String], startAt: Double) {
        queue.async { self.openSync(url: url, headers: headers, startAt: startAt) }
    }

    func play() {
        queue.async {
            self.wantsPlay = true
            guard self.state == .paused else { return }
            self.resumeClocks()
            self.state = .playing
        }
    }

    func pause() {
        queue.async {
            self.wantsPlay = false
            guard self.state == .playing else { return }
            self.holdClocks()
            self.state = .paused
        }
    }

    func togglePlayPause() {
        queue.async {
            switch self.state {
            case .playing:
                self.wantsPlay = false
                self.holdClocks()
                self.state = .paused
            case .paused, .ended:
                self.wantsPlay = true
                self.resumeClocks()
                self.state = .playing
            default:
                self.wantsPlay.toggle()
            }
        }
    }

    func seek(by delta: Double) {
        seek(to: currentSeconds + delta)
    }

    func seek(to target: Double) {
        queue.async {
            guard self.state != .idle, self.state != .opening else { return }
            let upperBound = self.durationSeconds > 1 ? self.durationSeconds - 1 : Double.greatestFiniteMagnitude
            let clamped = min(max(0, target), upperBound)
            // Bumping the generation first invalidates every packet that is
            // already in flight, even ones popped before the queues flush.
            let newGeneration = self.generation.get() + 1
            self.generation.set(newGeneration)
            self.holdClocks()
            self.state = .seeking
            self.eventSink.yield(.time(clamped))
            self.pendingSeek.set((target: clamped, generation: newGeneration))
        }
    }

    /// Position in seconds, derived from the video timebase (which is
    /// continuously slaved to the audio clock). Safe from any thread.
    var currentSeconds: Double { videoRenderer.currentSeconds }

    func stop() {
        guard !closed.exchange(true) else { return }
        demuxer.cancelToken.cancel()   // aborts a blocking av_read_frame/seek
        videoQueue.close()
        audioQueue.close()
        seekResume.signal()            // unblock a demux thread parked mid-seek
        queue.async {
            self.syncTimer?.cancel()
            self.syncTimer = nil
            self.videoRenderer.stopFeeding()
            self.videoRenderer.setRate(0)
            self.videoRenderer.flush()
            self.audioRenderer?.stop()
            // Let the worker threads drain out of their libav calls before
            // tearing the contexts down — avformat_close_input during a
            // running av_read_frame is a use-after-free.
            if self.demuxStarted {
                _ = self.demuxDone.wait(timeout: .now() + 3)
            }
            if self.audioStarted {
                _ = self.audioDone.wait(timeout: .now() + 3)
            }
            self.videoQueue.flush()
            self.audioQueue.flush()
            self.demuxer.close()
            self.state = .idle
            self.eventSink.finish()
        }
    }

    // MARK: - Open

    private func openSync(url: URL, headers: [String: String], startAt: Double) {
        state = .opening
        do {
            try demuxer.open(url: url.absoluteString, headers: headers)
            guard let videoStream = demuxer.video else {
                throw PlayerError.openFailed("kein Video-Stream")
            }
            guard videoStream.codecId == AV_CODEC_ID_H264 || videoStream.codecId == AV_CODEC_ID_HEVC else {
                throw PlayerError.unsupportedCodec("Video-Codec-ID \(videoStream.codecId.rawValue) (nur H.264/HEVC)")
            }
            videoFactory = try VideoSampleFactory(stream: videoStream)

            // Audio is best-effort — video-only beats a hard failure — but
            // the failure must surface in the UI, not vanish.
            if let audioStream = demuxer.audio {
                do {
                    let decoder = try AudioDecoder(stream: audioStream)
                    let ring = PCMRingBuffer(sampleRate: decoder.sampleRate)
                    let renderer = AudioRenderer(ring: ring)
                    try renderer.setUp()
                    audioDecoder = decoder
                    audioRing = ring
                    audioRenderer = renderer
                } catch {
                    audioDecoder = nil
                    audioRing = nil
                    audioRenderer = nil
                    eventSink.yield(.audioUnavailable(describe(error)))
                }
            } else {
                eventSink.yield(.audioUnavailable("Datei enthält keine Tonspur"))
            }

            if let duration = demuxer.durationSeconds {
                durationSeconds = duration
                eventSink.yield(.duration(duration))
            }
            if startAt > 0.5 {
                try? demuxer.seek(toSeconds: startAt)
            }
            videoRenderer.setTime(seconds: startAt)
            eventSink.yield(.time(startAt))

            startDemuxThread()
            startAudioThread()
            startVideoFeed()
            startSyncTimer()
            state = .buffering
            waitUntilBuffered()
        } catch {
            state = .failed(describe(error))
        }
    }

    private func describe(_ error: Error) -> String {
        if let ffError = error as? FFmpegError { return ffError.message }
        if let playerError = error as? PlayerError { return playerError.message }
        return error.localizedDescription
    }

    // MARK: - Buffering

    /// Polls until enough is buffered, then starts/holds the clocks.
    private func waitUntilBuffered() {
        guard !closed.get(), state == .buffering || state == .seeking else { return }
        let videoReady = !videoQueue.isEmpty
        let audioReady = audioRing.map { $0.availableSeconds > 0.3 || reachedEOF.get() || audioStartFailed } ?? true
        if (videoReady && audioReady) || (reachedEOF.get() && videoReady) {
            if wantsPlay {
                resumeClocks()
                state = .playing
            } else {
                state = .paused
            }
            return
        }
        queue.asyncAfter(deadline: .now() + 0.1) { [weak self] in
            self?.waitUntilBuffered()
        }
    }

    private func resumeClocks() {
        if let audioRenderer, !audioEngineRunning, !audioStartFailed {
            do {
                try audioRenderer.start()
                audioEngineRunning = true
            } catch {
                // Keep playing video-only off the free-running timebase.
                audioStartFailed = true
                eventSink.yield(.audioUnavailable(describe(error)))
            }
        }
        videoRenderer.setRate(1)
    }

    private func holdClocks() {
        audioRenderer?.pause()
        audioEngineRunning = false
        videoRenderer.setRate(0)
    }

    // MARK: - Demux thread

    private func startDemuxThread() {
        demuxStarted = true
        let thread = Thread { [weak self] in self?.demuxLoop() }
        thread.name = "vault.player.demux"
        thread.qualityOfService = .userInitiated
        thread.start()
    }

    private func demuxLoop() {
        defer { demuxDone.signal() }
        // Generation written into packet tags; advanced only after a seek
        // has been performed AND the engine has reset the consumers.
        var pushGeneration = 0

        while !closed.get(), !demuxer.cancelToken.isCancelled {
            if let request = pendingSeek.exchange(nil) {
                try? demuxer.seek(toSeconds: request.target)
                videoQueue.flush()
                audioQueue.flush()
                reachedEOF.set(false)
                queue.async { [weak self] in self?.finishSeek(at: request.target) }
                // Don't push new-generation packets until the engine has
                // reset ring buffer, clocks and display layer.
                while !closed.get(), seekResume.wait(timeout: .now() + 0.1) == .timedOut {}
                pushGeneration = request.generation
                continue
            }
            if reachedEOF.get() || videoQueue.isFull || audioQueue.isFull {
                Thread.sleep(forTimeInterval: 0.05)
                continue
            }
            do {
                guard let packet = try demuxer.readPacket() else {
                    reachedEOF.set(true)
                    continue
                }
                let streamIndex = packet.pointee.stream_index
                var pushed = false
                if let video = demuxer.video, streamIndex == video.index {
                    pushed = videoQueue.push(packet, generation: pushGeneration)
                } else if let audio = demuxer.audio, streamIndex == audio.index, audioDecoder != nil {
                    pushed = audioQueue.push(packet, generation: pushGeneration)
                }
                if !pushed {
                    var toFree: UnsafeMutablePointer<AVPacket>? = packet
                    av_packet_free(&toFree)
                }
            } catch {
                if !closed.get() {
                    let message = describe(error)
                    queue.async { [weak self] in self?.state = .failed(message) }
                }
                return
            }
        }
    }

    /// Engine queue: reset consumers after the demux thread sought and
    /// flushed. The demux thread is parked on `seekResume` meanwhile.
    private func finishSeek(at target: Double) {
        guard !closed.get() else {
            seekResume.signal()
            return
        }
        // The audio codec itself is flushed by the audio thread when it sees
        // the new generation tag — it is the codec's only user.
        audioRing?.reset()
        audioRenderer?.invalidateClock()
        videoRenderer.flush()
        waitingForKeyframe.set(true)
        videoRenderer.setTime(seconds: target)
        eventSink.yield(.time(target))
        state = .buffering
        seekResume.signal()
        waitUntilBuffered()
    }

    // MARK: - Audio thread

    private func startAudioThread() {
        guard audioDecoder != nil else { return }
        audioStarted = true
        let thread = Thread { [weak self] in self?.audioLoop() }
        thread.name = "vault.player.audio"
        thread.qualityOfService = .userInteractive
        thread.start()
    }

    private func audioLoop() {
        defer { audioDone.signal() }
        guard let decoder = audioDecoder, let ring = audioRing else { return }
        var lastTag = 0

        while !closed.get() {
            guard let entry = audioQueue.pop(wait: true) else {
                if closed.get() { return }
                // Woken by a flush — loop around.
                Thread.sleep(forTimeInterval: 0.01)
                continue
            }
            var toFree: UnsafeMutablePointer<AVPacket>? = entry.packet
            // Stale packet from before the latest seek: drop it.
            guard entry.generation == generation.get() else {
                av_packet_free(&toFree)
                continue
            }
            // First packet of a new generation: drop codec-internal state.
            if entry.generation != lastTag {
                decoder.flush()
                lastTag = entry.generation
            }
            let chunks = decoder.decode(packet: entry.packet)
            av_packet_free(&toFree)

            for chunk in chunks {
                var frameOffset = 0
                let totalFrames = chunk.samples.count / 2
                while frameOffset < totalFrames,
                      !closed.get(),
                      entry.generation == generation.get() {
                    let written = ring.write(chunk.samples, fromFrame: frameOffset, pts: chunk.pts)
                    if written == 0 {
                        // Ring full — back off until the render callback drains it.
                        Thread.sleep(forTimeInterval: 0.05)
                    } else {
                        frameOffset += written
                    }
                }
                if entry.generation != generation.get() { break }
            }
        }
    }

    // MARK: - Video feed

    private func startVideoFeed() {
        videoRenderer.startFeeding { [weak self] in
            self?.nextVideoSample()
        }
    }

    /// Called on the video feed queue whenever the layer wants more data.
    private func nextVideoSample() -> CMSampleBuffer? {
        guard let factory = videoFactory else { return nil }
        while !closed.get() {
            guard let entry = videoQueue.pop(wait: false) else { return nil }
            defer {
                var toFree: UnsafeMutablePointer<AVPacket>? = entry.packet
                av_packet_free(&toFree)
            }
            // Stale packet from before the latest seek: drop it.
            guard entry.generation == generation.get() else { continue }
            if waitingForKeyframe.get() {
                guard entry.packet.pointee.flags & FF.pktFlagKey != 0 else { continue }
                waitingForKeyframe.set(false)
            }
            guard let sample = try? factory.makeSampleBuffer(packet: entry.packet), let sample else {
                continue
            }
            return sample
        }
        return nil
    }

    // MARK: - Sync timer

    private func startSyncTimer() {
        let timer = DispatchSource.makeTimerSource(queue: queue)
        timer.schedule(deadline: .now() + 0.25, repeating: 0.25)
        timer.setEventHandler { [weak self] in self?.tick() }
        timer.resume()
        syncTimer = timer
    }

    private func tick() {
        guard !closed.get() else { return }

        eventSink.yield(.time(currentSeconds))

        if videoRenderer.didFail {
            holdClocks()
            state = .failed("Video-Decoder-Fehler (Display-Layer)")
            return
        }

        // Slave the video timebase to the audio clock.
        if state == .playing,
           let audioClock = audioRenderer?.clockSeconds,
           let timebase = videoRenderer.timebase {
            let drift = CMTimebaseGetTime(timebase).seconds - audioClock
            if abs(drift) > 0.1 {
                CMTimebaseSetTime(timebase, time: CMTime(seconds: audioClock, preferredTimescale: 90000))
            }
        }

        // End of playback: EOF reached and both pipelines drained.
        if state == .playing,
           reachedEOF.get(),
           videoQueue.isEmpty,
           audioStartFailed || (audioRing?.availableFrames ?? 0) == 0,
           durationSeconds > 0,
           currentSeconds >= durationSeconds - 1 {
            holdClocks()
            state = .ended
        }
    }
}
