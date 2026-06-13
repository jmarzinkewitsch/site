import Foundation
import os

/// Ring buffer of interleaved stereo Float32 PCM with PTS tracking.
/// Written by the audio decode thread, read by the AVAudioSourceNode render
/// callback. `headPTS` is the presentation time of the frame at the read
/// head and advances as frames are consumed — that is the audio clock.
final class PCMRingBuffer {
    private let channels = 2
    let sampleRate: Double
    private let capacityFrames: Int
    private var storage: [Float]
    private var readIndex = 0
    private var writeIndex = 0
    private var framesStored = 0
    private var headPTS: Double = .nan
    private var lock = os_unfair_lock_s()

    init(sampleRate: Double, seconds: Double = 4) {
        self.sampleRate = sampleRate
        capacityFrames = max(1, Int(sampleRate * seconds))
        storage = [Float](repeating: 0, count: capacityFrames * channels)
    }

    var availableFrames: Int {
        os_unfair_lock_lock(&lock); defer { os_unfair_lock_unlock(&lock) }
        return framesStored
    }

    var availableSeconds: Double {
        Double(availableFrames) / sampleRate
    }

    /// Writes as much as fits, starting at `fromFrame` within `samples`.
    /// Returns the number of frames written.
    func write(_ samples: [Float], fromFrame: Int, pts: Double?) -> Int {
        let totalFrames = samples.count / channels
        guard fromFrame < totalFrames else { return 0 }
        os_unfair_lock_lock(&lock); defer { os_unfair_lock_unlock(&lock) }

        if framesStored == 0, let pts {
            headPTS = pts + Double(fromFrame) / sampleRate
        }
        let framesToWrite = min(totalFrames - fromFrame, capacityFrames - framesStored)
        guard framesToWrite > 0 else { return 0 }

        samples.withUnsafeBufferPointer { source in
            var sourceOffset = fromFrame * channels
            var remaining = framesToWrite
            while remaining > 0 {
                let chunk = min(remaining, capacityFrames - writeIndex)
                storage.withUnsafeMutableBufferPointer { dest in
                    dest.baseAddress!.advanced(by: writeIndex * channels)
                        .update(from: source.baseAddress!.advanced(by: sourceOffset), count: chunk * channels)
                }
                writeIndex = (writeIndex + chunk) % capacityFrames
                sourceOffset += chunk * channels
                remaining -= chunk
            }
        }
        framesStored += framesToWrite
        return framesToWrite
    }

    /// Fills `pointer` with `frames` frames (zero-padding any shortfall).
    /// Returns frames actually read and the PTS at the read head before reading.
    func read(into pointer: UnsafeMutablePointer<Float>, frames: Int) -> (framesRead: Int, pts: Double) {
        os_unfair_lock_lock(&lock)
        let framesToRead = min(frames, framesStored)
        let pts = headPTS
        var destOffset = 0
        var remaining = framesToRead
        while remaining > 0 {
            let chunk = min(remaining, capacityFrames - readIndex)
            storage.withUnsafeBufferPointer { source in
                pointer.advanced(by: destOffset)
                    .update(from: source.baseAddress!.advanced(by: readIndex * channels), count: chunk * channels)
            }
            readIndex = (readIndex + chunk) % capacityFrames
            destOffset += chunk * channels
            remaining -= chunk
        }
        framesStored -= framesToRead
        if !pts.isNaN {
            headPTS = pts + Double(framesToRead) / sampleRate
        }
        os_unfair_lock_unlock(&lock)

        if framesToRead < frames {
            pointer.advanced(by: framesToRead * channels)
                .update(repeating: 0, count: (frames - framesToRead) * channels)
        }
        return (framesToRead, pts)
    }

    func reset() {
        os_unfair_lock_lock(&lock); defer { os_unfair_lock_unlock(&lock) }
        readIndex = 0
        writeIndex = 0
        framesStored = 0
        headPTS = .nan
    }
}
