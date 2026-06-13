import Foundation
import Libavcodec

/// Thread-safe FIFO of demuxed AVPackets, bounded by total byte size.
/// The demux thread pushes (and backs off via `isFull`), the video feeder
/// pops non-blocking, the audio decode thread pops blocking.
///
/// Entries carry the seek generation they were demuxed under (tagged at
/// enqueue time) so consumers can drop packets that belong to a position
/// before the most recent seek, even if they were popped mid-flush.
/// Packets are owned by the queue once pushed; poppers must free them.
final class PacketQueue {
    struct Entry {
        let packet: UnsafeMutablePointer<AVPacket>
        let generation: Int
    }

    private let condition = NSCondition()
    private var entries: [Entry] = []
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
        return entries.count == head
    }

    /// Takes ownership of the packet. Returns false (caller must free) if closed.
    @discardableResult
    func push(_ packet: UnsafeMutablePointer<AVPacket>, generation: Int) -> Bool {
        condition.lock(); defer { condition.unlock() }
        guard !closed else { return false }
        entries.append(Entry(packet: packet, generation: generation))
        bytes += Int(packet.pointee.size)
        condition.signal()
        return true
    }

    /// Pops the next entry; with `wait` blocks until data arrives, the queue
    /// is flushed (may return nil) or closed (returns nil).
    func pop(wait: Bool) -> Entry? {
        condition.lock(); defer { condition.unlock() }
        if wait {
            while entries.count == head && !closed {
                condition.wait()
            }
        }
        guard entries.count > head else { return nil }
        let entry = entries[head]
        head += 1
        bytes -= Int(entry.packet.pointee.size)
        if head > 64 {
            entries.removeFirst(head)
            head = 0
        }
        return entry
    }

    func flush() {
        condition.lock(); defer { condition.unlock() }
        for index in head..<entries.count {
            var packet: UnsafeMutablePointer<AVPacket>? = entries[index].packet
            av_packet_free(&packet)
        }
        entries.removeAll()
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
