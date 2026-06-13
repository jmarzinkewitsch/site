import XCTest
@testable import Vault

final class PCMRingBufferTests: XCTestCase {
    /// Tiny ring: 8 frames capacity (sampleRate 8 × 1 s), stereo interleaved.
    private func makeRing() -> PCMRingBuffer {
        PCMRingBuffer(sampleRate: 8, seconds: 1)
    }

    /// Interleaved stereo test signal: frame n = [n, n + 0.5].
    private func frames(_ range: Range<Int>) -> [Float] {
        range.flatMap { [Float($0), Float($0) + 0.5] }
    }

    private func read(_ ring: PCMRingBuffer, frames count: Int) -> (framesRead: Int, pts: Double, samples: [Float]) {
        var buffer = [Float](repeating: -1, count: count * 2)
        let result = buffer.withUnsafeMutableBufferPointer { pointer in
            ring.read(into: pointer.baseAddress!, frames: count)
        }
        return (result.framesRead, result.pts, buffer)
    }

    func testWriteReadRoundtrip() {
        let ring = makeRing()
        XCTAssertEqual(ring.write(frames(0..<4), fromFrame: 0, pts: 10.0), 4)
        XCTAssertEqual(ring.availableFrames, 4)

        let result = read(ring, frames: 4)
        XCTAssertEqual(result.framesRead, 4)
        XCTAssertEqual(result.pts, 10.0, accuracy: 1e-9)
        XCTAssertEqual(result.samples, frames(0..<4))
        XCTAssertEqual(ring.availableFrames, 0)
    }

    func testPartialWriteWhenFull() {
        let ring = makeRing()
        XCTAssertEqual(ring.write(frames(0..<8), fromFrame: 0, pts: 0), 8)
        // Full: nothing more fits.
        XCTAssertEqual(ring.write(frames(8..<10), fromFrame: 0, pts: 1.0), 0)
        // Drain 2 frames, then exactly 2 fit.
        _ = read(ring, frames: 2)
        XCTAssertEqual(ring.write(frames(8..<12), fromFrame: 0, pts: 1.0), 2)
    }

    func testFromFrameOffsetSkipsAlreadyWrittenFrames() {
        let ring = makeRing()
        let data = frames(0..<6)
        XCTAssertEqual(ring.write(data, fromFrame: 4, pts: nil), 2)
        let result = read(ring, frames: 2)
        XCTAssertEqual(result.samples, frames(4..<6))
    }

    func testWraparoundKeepsOrder() {
        let ring = makeRing()
        XCTAssertEqual(ring.write(frames(0..<6), fromFrame: 0, pts: 0), 6)
        XCTAssertEqual(read(ring, frames: 4).samples, frames(0..<4))
        // Write 5 frames: 2 fit at the tail, 3 wrap to the front.
        XCTAssertEqual(ring.write(frames(6..<11), fromFrame: 0, pts: nil), 5)
        let result = read(ring, frames: 7)
        XCTAssertEqual(result.framesRead, 7)
        XCTAssertEqual(result.samples, frames(4..<11))
    }

    func testZeroPaddingOnUnderrun() {
        let ring = makeRing()
        XCTAssertEqual(ring.write(frames(0..<2), fromFrame: 0, pts: 5.0), 2)
        let result = read(ring, frames: 4)
        XCTAssertEqual(result.framesRead, 2)
        XCTAssertEqual(Array(result.samples[0..<4]), frames(0..<2))
        XCTAssertEqual(Array(result.samples[4..<8]), [0, 0, 0, 0])
    }

    func testPTSAdvancesWithConsumedFrames() {
        let ring = makeRing()
        _ = ring.write(frames(0..<8), fromFrame: 0, pts: 100.0)
        XCTAssertEqual(read(ring, frames: 4).pts, 100.0, accuracy: 1e-9)
        // 4 frames at 8 Hz = 0.5 s consumed.
        XCTAssertEqual(read(ring, frames: 4).pts, 100.5, accuracy: 1e-9)
    }

    func testResetClearsDataAndPTS() {
        let ring = makeRing()
        _ = ring.write(frames(0..<4), fromFrame: 0, pts: 50.0)
        ring.reset()
        XCTAssertEqual(ring.availableFrames, 0)
        let result = read(ring, frames: 2)
        XCTAssertEqual(result.framesRead, 0)
        XCTAssertTrue(result.pts.isNaN)
        // PTS restarts from the first write after reset.
        _ = ring.write(frames(0..<2), fromFrame: 0, pts: 7.0)
        XCTAssertEqual(read(ring, frames: 2).pts, 7.0, accuracy: 1e-9)
    }
}
