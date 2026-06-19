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

    // Pre-allocated scratch buffer for the render callback (interleaved L,R
    // pairs). Sized for the maximum expected frameCount on tvOS (4096) times
    // 2 channels so the audio thread never has to heap-allocate.
    private static let maxFrames = 4096
    private var scratchBuffer: UnsafeMutablePointer<Float> =
        .allocate(capacity: AudioRenderer.maxFrames * 2)

    init(ring: PCMRingBuffer) {
        self.ring = ring
    }

    deinit {
        scratchBuffer.deallocate()
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
            interleaved: false
        ) else {
            throw PlayerError.audioSetup("AVAudioFormat")
        }

        let ring = self.ring
        let clock = self.clock
        // Capture the raw pointer and capacity so the render callback holds no
        // reference to self and performs no ARC operations on the audio thread.
        let scratch = self.scratchBuffer
        let scratchCapacity = AudioRenderer.maxFrames
        let node = AVAudioSourceNode(format: format) { _, _, frameCount, audioBufferList -> OSStatus in
            let buffers = UnsafeMutableAudioBufferListPointer(audioBufferList)
            let requestedFrames = min(Int(frameCount), scratchCapacity)
            let (framesRead, pts) = ring.read(into: scratch, frames: requestedFrames)

            if buffers.count >= 2,
               let leftData = buffers[0].mData,
               let rightData = buffers[1].mData {
                let left = leftData.assumingMemoryBound(to: Float.self)
                let right = rightData.assumingMemoryBound(to: Float.self)
                for frame in 0..<requestedFrames {
                    if frame < framesRead {
                        left[frame] = scratch[frame * 2]
                        right[frame] = scratch[frame * 2 + 1]
                    } else {
                        left[frame] = 0
                        right[frame] = 0
                    }
                }
                let byteSize = UInt32(requestedFrames * MemoryLayout<Float>.size)
                buffers[0].mDataByteSize = byteSize
                buffers[1].mDataByteSize = byteSize
            } else if let rawData = buffers[0].mData {
                let output = rawData.assumingMemoryBound(to: Float.self)
                let sampleCount = requestedFrames * 2
                for sample in 0..<sampleCount {
                    output[sample] = sample < framesRead * 2 ? scratch[sample] : 0
                }
                buffers[0].mDataByteSize = UInt32(sampleCount * MemoryLayout<Float>.size)
            }

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
