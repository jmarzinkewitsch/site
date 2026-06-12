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
}

/// Orchestrates demuxing, video sample feeding, audio decoding and A/V sync.
///
/// Threads:
/// - engine queue (serial): state machine, open/seek/play/pause, sync timer
/// - demux thread: av_read_frame loop + av_seek_frame
/// - audio thread: packet → PCM → ring buffer
/// - video feed queue (in VideoRenderer): packet → CMSampleBuffer → layer
/// - audio render callback (in AudioRenderer): ring buffer → speaker, clock
///
/// Clocking: audio is master. Video runs off the display layer's CMTimebase,
/// which the sync timer slaves to the audio clock.
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
    private var syncTimer: DispatchSourceTimer?

    private let closed = AtomicValue(false)
    private let reachedEOF = AtomicValue(false)
    private let waitingForKeyframe = AtomicValue(true)
    private let pendingSeek = AtomicValue<Double?>(nil)
    private let generation = AtomicValue(0)

    init() {
        (events, eventSink) = AsyncStream.makeStream(of: PlayerEvent.self)
    }

    // MARK: - Public API

    /// Main thread: wire up the display layer before/while opening.
    func attach(layer: AVSampleBufferDisplayLayer) {
        try? videoRenderer.attach(layer: layer)
    }

    func open(url: URL, startAt: Double) {
        queue.async { self.openSync(url: url, startAt: startAt) }
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
            self.generation.set(self.generation.get() + 1)
            self.holdClocks()
            self.state = .seeking
            self.eventSink.yield(.time(clamped))
            // The demux thread picks this up, seeks, flushes the queues and
            // calls back into finishSeek on the engine queue.
            self.pendingSeek.set(clamped)
        }
    }

    /// Position in seconds, derived from the video timebase (which is
    /// continuously slaved to the audio clock). Safe from any thread.
    var currentSeconds: Double { videoRenderer.currentSeconds }

    func stop() {
        guard !closed.exchange(true) else { return }
        demuxer.cancelToken.cancel()
        videoQueue.close()
        audioQueue.close()
        queue.async {
            self.syncTimer?.cancel()
            self.syncTimer = nil
            self.videoRenderer.stopFeeding()
            self.videoRenderer.setRate(0)
            self.videoRenderer.flush()
            self.audioRenderer?.stop()
            self.videoQueue.flush()
            self.audioQueue.flush()
            self.demuxer.close()
            self.state = .idle
            self.eventSink.finish()
        }
    }

    // MARK: - Open

    private func openSync(url: URL, startAt: Double) {
        state = .opening
        do {
            try demuxer.open(url: url.absoluteString)
            guard let videoStream = demuxer.video else {
                throw PlayerError.openFailed("kein Video-Stream")
            }
            guard videoStream.codecId == AV_CODEC_ID_H264 || videoStream.codecId == AV_CODEC_ID_HEVC else {
                throw PlayerError.unsupportedCodec("Video-Codec-ID \(videoStream.codecId.rawValue) (nur H.264/HEVC)")
            }
            videoFactory = try VideoSampleFactory(stream: videoStream)

            // Audio is best-effort: silent video beats a hard failure.
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
                }
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
        let audioReady = audioRing.map { $0.availableSeconds > 0.3 || reachedEOF.get() } ?? true
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
        if let audioRenderer, !audioEngineRunning {
            try? audioRenderer.start()
            audioEngineRunning = true
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
        let thread = Thread { [weak self] in self?.demuxLoop() }
        thread.name = "vault.player.demux"
        thread.qualityOfService = .userInitiated
        thread.start()
    }

    private func demuxLoop() {
        while !closed.get(), !demuxer.cancelToken.isCancelled {
            if let target = pendingSeek.exchange(nil) {
                try? demuxer.seek(toSeconds: target)
                videoQueue.flush()
                audioQueue.flush()
                reachedEOF.set(false)
                queue.async { [weak self] in self?.finishSeek(at: target) }
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
                    pushed = videoQueue.push(packet)
                } else if let audio = demuxer.audio, streamIndex == audio.index, audioDecoder != nil {
                    pushed = audioQueue.push(packet)
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

    /// Engine queue: reset decoders/clocks after the demux thread has sought.
    private func finishSeek(at target: Double) {
        guard !closed.get() else { return }
        audioDecoder?.flush()
        audioRing?.reset()
        audioRenderer?.invalidateClock()
        videoRenderer.flush()
        waitingForKeyframe.set(true)
        videoRenderer.setTime(seconds: target)
        eventSink.yield(.time(target))
        state = .buffering
        waitUntilBuffered()
    }

    // MARK: - Audio thread

    private func startAudioThread() {
        guard audioDecoder != nil else { return }
        let thread = Thread { [weak self] in self?.audioLoop() }
        thread.name = "vault.player.audio"
        thread.qualityOfService = .userInteractive
        thread.start()
    }

    private func audioLoop() {
        guard let decoder = audioDecoder, let ring = audioRing else { return }
        while !closed.get() {
            guard let packet = audioQueue.pop(wait: true) else {
                if closed.get() { return }
                // Woken by a flush — loop around.
                Thread.sleep(forTimeInterval: 0.01)
                continue
            }
            let packetGeneration = generation.get()
            let chunks = decoder.decode(packet: packet)
            var toFree: UnsafeMutablePointer<AVPacket>? = packet
            av_packet_free(&toFree)

            for chunk in chunks {
                var frameOffset = 0
                let totalFrames = chunk.samples.count / 2
                while frameOffset < totalFrames,
                      !closed.get(),
                      packetGeneration == generation.get() {
                    let written = ring.write(chunk.samples, fromFrame: frameOffset, pts: chunk.pts)
                    if written == 0 {
                        // Ring full — back off until the render callback drains it.
                        Thread.sleep(forTimeInterval: 0.05)
                    } else {
                        frameOffset += written
                    }
                }
                if packetGeneration != generation.get() { break }
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
            guard let packet = videoQueue.pop(wait: false) else { return nil }
            defer {
                var toFree: UnsafeMutablePointer<AVPacket>? = packet
                av_packet_free(&toFree)
            }
            if waitingForKeyframe.get() {
                guard packet.pointee.flags & FF.pktFlagKey != 0 else { continue }
                waitingForKeyframe.set(false)
            }
            guard let sample = try? factory.makeSampleBuffer(packet: packet), let sample else {
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
           (audioRing?.availableFrames ?? 0) == 0,
           durationSeconds > 0,
           currentSeconds >= durationSeconds - 1 {
            holdClocks()
            state = .ended
        }
    }
}
