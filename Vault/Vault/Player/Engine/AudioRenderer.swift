import AVFAudio
import Foundation

/// Plays PCM from the ring buffer through AVAudioEngine and exposes the
/// audio clock (PTS of the sample currently hitting the speaker, latency-
/// compensated). The audio clock is the playback master clock.
final class AudioRenderer {
    private let engine = AVAudioEngine()
    private var sourceNode: AVAudioSourceNode?
    let ring: PCMRingBuffer
    private let clock = AtomicValue<Double?>(nil)

    init(ring: PCMRingBuffer) {
        self.ring = ring
    }

    /// nil until the first buffer actually rendered.
    var clockSeconds: Double? { clock.get() }

    func setUp() throws {
        let session = AVAudioSession.sharedInstance()
        do {
            try session.setCategory(.playback, mode: .moviePlayback)
            try session.setActive(true)
        } catch {
            throw PlayerError.audioSetup("AVAudioSession: \(error.localizedDescription)")
        }
        let outputLatency = session.outputLatency

        guard let format = AVAudioFormat(
            commonFormat: .pcmFormatFloat32,
            sampleRate: ring.sampleRate,
            channels: 2,
            interleaved: true
        ) else {
            throw PlayerError.audioSetup("AVAudioFormat")
        }

        let ring = self.ring
        let clock = self.clock
        let node = AVAudioSourceNode(format: format) { _, _, frameCount, audioBufferList -> OSStatus in
            let buffers = UnsafeMutableAudioBufferListPointer(audioBufferList)
            guard let rawData = buffers[0].mData else { return noErr }
            let data = rawData.assumingMemoryBound(to: Float.self)
            let (framesRead, pts) = ring.read(into: data, frames: Int(frameCount))
            buffers[0].mDataByteSize = UInt32(Int(frameCount) * 2 * MemoryLayout<Float>.size)
            if !pts.isNaN, framesRead > 0 {
                clock.set(pts + Double(framesRead) / ring.sampleRate - outputLatency)
            }
            return noErr
        }
        engine.attach(node)
        engine.connect(node, to: engine.mainMixerNode, format: format)
        sourceNode = node
        engine.prepare()
    }

    func start() throws {
        do {
            try engine.start()
        } catch {
            throw PlayerError.audioSetup("engine.start: \(error.localizedDescription)")
        }
    }

    func pause() {
        engine.pause()
    }

    func stop() {
        engine.stop()
        clock.set(nil)
    }

    func invalidateClock() {
        clock.set(nil)
    }
}
