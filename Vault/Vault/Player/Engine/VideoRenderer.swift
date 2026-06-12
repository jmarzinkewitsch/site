import AVFoundation
import CoreMedia
import Foundation

/// Feeds compressed CMSampleBuffers into an AVSampleBufferDisplayLayer and
/// owns its control timebase. The timebase rate/time is the video clock;
/// PlaybackEngine periodically slaves it to the audio clock.
final class VideoRenderer {
    private weak var layer: AVSampleBufferDisplayLayer?
    private(set) var timebase: CMTimebase?
    private let feedQueue = DispatchQueue(label: "vault.player.videofeed")
    private let feeding = AtomicValue(false)

    /// Must be called on the main thread with the layer from the view.
    func attach(layer: AVSampleBufferDisplayLayer) throws {
        self.layer = layer
        var timebase: CMTimebase?
        let status = CMTimebaseCreateWithSourceClock(
            allocator: kCFAllocatorDefault,
            sourceClock: CMClockGetHostTimeClock(),
            timebaseOut: &timebase
        )
        guard status == 0, let timebase else { throw PlayerError.sampleBuffer(status) }
        CMTimebaseSetRate(timebase, rate: 0)
        CMTimebaseSetTime(timebase, time: .zero)
        layer.controlTimebase = timebase
        self.timebase = timebase
    }

    var isAttached: Bool { layer != nil }

    /// `supplier` is called on the feed queue and returns the next sample
    /// buffer or nil when no data is available right now.
    func startFeeding(supplier: @escaping () -> CMSampleBuffer?) {
        guard let layer else { return }
        feeding.set(true)
        layer.requestMediaDataWhenReady(on: feedQueue) { [weak layer, feeding] in
            guard let layer, feeding.get() else { return }
            while layer.isReadyForMoreMediaData {
                guard let sample = supplier() else { break }
                layer.enqueue(sample)
            }
        }
    }

    func stopFeeding() {
        feeding.set(false)
        layer?.stopRequestingMediaData()
    }

    func flush() {
        layer?.flush()
    }

    var didFail: Bool { layer?.status == .failed }

    func setRate(_ rate: Double) {
        guard let timebase else { return }
        CMTimebaseSetRate(timebase, rate: rate)
    }

    func setTime(seconds: Double) {
        guard let timebase else { return }
        CMTimebaseSetTime(timebase, time: CMTime(seconds: seconds, preferredTimescale: 90000))
    }

    var currentSeconds: Double {
        guard let timebase else { return 0 }
        return CMTimebaseGetTime(timebase).seconds
    }
}
