import Foundation
import Libavcodec

/// Thread-safe FIFO of demuxed AVPackets, bounded by total byte size.
/// The demux thread pushes (and backs off via `isFull`), the video feeder
/// pops non-blocking, the audio decode thread pops blocking.
/// Packets are owned by the queue once pushed; poppers must free them.
final class PacketQueue {
    private let condition = NSCondition()
    private var packets: [UnsafeMutablePointer<AVPacket>] = []
    private var head = 0
    private var bytes = 0
    private var closed = false
    let maxBytes: Int

    init(maxBytes: Int) {
        self.maxBytes = maxBytes
    }

    var isFull: Bool {
        condition.lock(); defer { condition.unlock() }
        return bytes >= maxBytes
    }

    var isEmpty: Bool {
        condition.lock(); defer { condition.unlock() }
        return packets.count == head
    }

    /// Takes ownership of the packet. Returns false (caller must free) if closed.
    @discardableResult
    func push(_ packet: UnsafeMutablePointer<AVPacket>) -> Bool {
        condition.lock(); defer { condition.unlock() }
        guard !closed else { return false }
        packets.append(packet)
        bytes += Int(packet.pointee.size)
        condition.signal()
        return true
    }

    /// Pops the next packet; with `wait` blocks until data arrives, the queue
    /// is flushed (returns nil) or closed (returns nil).
    func pop(wait: Bool) -> UnsafeMutablePointer<AVPacket>? {
        condition.lock(); defer { condition.unlock() }
        if wait {
            while packets.count == head && !closed {
                condition.wait()
            }
        }
        guard packets.count > head else { return nil }
        let packet = packets[head]
        head += 1
        bytes -= Int(packet.pointee.size)
        if head > 64 {
            packets.removeFirst(head)
            head = 0
        }
        return packet
    }

    func flush() {
        condition.lock(); defer { condition.unlock() }
        for index in head..<packets.count {
            var packet: UnsafeMutablePointer<AVPacket>? = packets[index]
            av_packet_free(&packet)
        }
        packets.removeAll()
        head = 0
        bytes = 0
        condition.broadcast()
    }

    /// Wakes all waiters; subsequent pushes are rejected. Call flush() after.
    func close() {
        condition.lock()
        closed = true
        condition.broadcast()
        condition.unlock()
    }
}
