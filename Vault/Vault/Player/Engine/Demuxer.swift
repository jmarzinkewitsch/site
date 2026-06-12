import Foundation
import Libavcodec
import Libavformat
import Libavutil

/// Cancellation flag polled by libavformat's interrupt callback so that
/// blocking network I/O (open, read, seek) can be aborted.
final class DemuxCancelToken {
    private let lock = NSLock()
    private var cancelled = false

    var isCancelled: Bool {
        lock.lock(); defer { lock.unlock() }
        return cancelled
    }

    func cancel() {
        lock.lock(); defer { lock.unlock() }
        cancelled = true
    }
}

private let ffInterruptCallback: @convention(c) (UnsafeMutableRawPointer?) -> Int32 = { opaque in
    guard let opaque else { return 0 }
    let token = Unmanaged<DemuxCancelToken>.fromOpaque(opaque).takeUnretainedValue()
    return token.isCancelled ? 1 : 0
}

/// Thin wrapper around AVFormatContext: open a URL, pick best video/audio
/// streams, read packets, seek. All calls are blocking — the engine drives
/// this from a dedicated thread.
final class Demuxer {
    struct Stream {
        let index: Int32
        let timeBase: AVRational
        let codecId: AVCodecID
        let codecpar: UnsafeMutablePointer<AVCodecParameters>
    }

    private(set) var video: Stream?
    private(set) var audio: Stream?
    private(set) var durationSeconds: Double?
    let cancelToken = DemuxCancelToken()
    private var context: UnsafeMutablePointer<AVFormatContext>?

    func open(url: String) throws {
        avformat_network_init()

        var formatContext = avformat_alloc_context()
        guard formatContext != nil else { throw PlayerError.openFailed("alloc context") }
        formatContext!.pointee.interrupt_callback = AVIOInterruptCB(
            callback: ffInterruptCallback,
            opaque: Unmanaged.passUnretained(cancelToken).toOpaque()
        )

        var options: OpaquePointer?
        av_dict_set(&options, "user_agent", "Vault/0.1", 0)
        av_dict_set(&options, "reconnect", "1", 0)
        let openResult = avformat_open_input(&formatContext, url, nil, &options)
        av_dict_free(&options)
        try ffCheck(openResult, "avformat_open_input")
        context = formatContext

        try ffCheck(avformat_find_stream_info(formatContext, nil), "avformat_find_stream_info")

        let videoIndex = av_find_best_stream(formatContext, AVMEDIA_TYPE_VIDEO, -1, -1, nil, 0)
        if videoIndex >= 0, let stream = formatContext!.pointee.streams[Int(videoIndex)] {
            video = Stream(
                index: videoIndex,
                timeBase: stream.pointee.time_base,
                codecId: stream.pointee.codecpar.pointee.codec_id,
                codecpar: stream.pointee.codecpar
            )
        }
        let audioIndex = av_find_best_stream(formatContext, AVMEDIA_TYPE_AUDIO, -1, videoIndex, nil, 0)
        if audioIndex >= 0, let stream = formatContext!.pointee.streams[Int(audioIndex)] {
            audio = Stream(
                index: audioIndex,
                timeBase: stream.pointee.time_base,
                codecId: stream.pointee.codecpar.pointee.codec_id,
                codecpar: stream.pointee.codecpar
            )
        }

        let duration = formatContext!.pointee.duration
        if duration > 0 {
            durationSeconds = Double(duration) / Double(FF.timeBase)
        }
    }

    /// Reads the next packet (caller owns it). Returns nil at EOF.
    func readPacket() throws -> UnsafeMutablePointer<AVPacket>? {
        guard let context else { return nil }
        guard let packet = av_packet_alloc() else { throw PlayerError.openFailed("alloc packet") }
        let result = av_read_frame(context, packet)
        if result < 0 {
            var toFree: UnsafeMutablePointer<AVPacket>? = packet
            av_packet_free(&toFree)
            if result == FF.eof { return nil }
            throw FFmpegError(code: result, context: "av_read_frame")
        }
        return packet
    }

    func seek(toSeconds target: Double) throws {
        guard let context else { return }
        let timestamp = Int64(target * Double(FF.timeBase))
        try ffCheck(av_seek_frame(context, -1, timestamp, FF.seekBackward), "av_seek_frame")
    }

    func close() {
        cancelToken.cancel()
        if context != nil {
            avformat_close_input(&context)
        }
    }
}
