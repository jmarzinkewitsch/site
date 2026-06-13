import Libavcodec
import XCTest
@testable import Vault

final class PacketQueueTests: XCTestCase {
    private func makePacket(size: Int32) -> UnsafeMutablePointer<AVPacket> {
        let packet = av_packet_alloc()!
        XCTAssertEqual(av_new_packet(packet, size), 0)
        return packet
    }

    private func free(_ entry: PacketQueue.Entry) {
        var packet: UnsafeMutablePointer<AVPacket>? = entry.packet
        av_packet_free(&packet)
    }

    func testFIFOOrderAndGenerationTags() {
        let queue = PacketQueue(maxBytes: 1 << 20)
        let first = makePacket(size: 10)
        let second = makePacket(size: 20)
        XCTAssertTrue(queue.push(first, generation: 0))
        XCTAssertTrue(queue.push(second, generation: 1))

        let poppedFirst = queue.pop(wait: false)
        XCTAssertEqual(poppedFirst?.packet, first)
        XCTAssertEqual(poppedFirst?.generation, 0)
        let poppedSecond = queue.pop(wait: false)
        XCTAssertEqual(poppedSecond?.packet, second)
        XCTAssertEqual(poppedSecond?.generation, 1)

        poppedFirst.map(free)
        poppedSecond.map(free)
    }

    func testByteLimitDrivesIsFull() {
        let queue = PacketQueue(maxBytes: 64)
        queue.push(makePacket(size: 40), generation: 0)
        XCTAssertFalse(queue.isFull)
        queue.push(makePacket(size: 40), generation: 0)
        XCTAssertTrue(queue.isFull)
        // Draining drops below the limit again.
        queue.pop(wait: false).map(free)
        XCTAssertFalse(queue.isFull)
        queue.flush()
    }

    func testNonBlockingPopOnEmptyReturnsNil() {
        let queue = PacketQueue(maxBytes: 64)
        XCTAssertNil(queue.pop(wait: false))
        XCTAssertTrue(queue.isEmpty)
    }

    func testFlushEmptiesQueue() {
        let queue = PacketQueue(maxBytes: 1 << 20)
        queue.push(makePacket(size: 8), generation: 0)
        queue.push(makePacket(size: 8), generation: 0)
        queue.flush()
        XCTAssertTrue(queue.isEmpty)
        XCTAssertNil(queue.pop(wait: false))
        XCTAssertFalse(queue.isFull)
    }

    func testCloseWakesBlockedPopAndRejectsPush() {
        let queue = PacketQueue(maxBytes: 64)
        let unblocked = expectation(description: "blocking pop returns after close")

        Thread.detachNewThread {
            let entry = queue.pop(wait: true)
            XCTAssertNil(entry)
            unblocked.fulfill()
        }
        // Give the worker a moment to actually block.
        Thread.sleep(forTimeInterval: 0.1)
        queue.close()
        wait(for: [unblocked], timeout: 2)

        // Pushes after close are rejected; ownership stays with the caller.
        let rejected = makePacket(size: 8)
        XCTAssertFalse(queue.push(rejected, generation: 0))
        var toFree: UnsafeMutablePointer<AVPacket>? = rejected
        av_packet_free(&toFree)
    }

    func testBlockingPopReceivesLatePush() {
        let queue = PacketQueue(maxBytes: 64)
        let received = expectation(description: "blocking pop gets the packet")

        Thread.detachNewThread {
            if let entry = queue.pop(wait: true) {
                XCTAssertEqual(entry.generation, 3)
                self.free(entry)
                received.fulfill()
            }
        }
        Thread.sleep(forTimeInterval: 0.1)
        queue.push(makePacket(size: 8), generation: 3)
        wait(for: [received], timeout: 2)
        queue.close()
    }
}
