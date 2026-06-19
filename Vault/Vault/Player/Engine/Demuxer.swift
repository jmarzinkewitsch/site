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
    private(set) var subtitles: [Stream] = []
    private(set) var durationSeconds: Double?
    let cancelToken = DemuxCancelToken()
    private var context: UnsafeMutablePointer<AVFormatContext>?

    /// `headers` are sent on every HTTP request (auth goes here instead of
    /// into the URL, so tokens never end up in server access logs).
    func open(url: String, headers: [String: String] = [:], audioStreamIndex: Int32? = nil) throws {
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
        if !headers.isEmpty {
            let headerLines = headers.map { "\($0.key): \($0.value)\r\n" }.joined()
            av_dict_set(&options, "headers", headerLines, 0)
        }
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
        let bestAudioIndex = av_find_best_stream(formatContext, AVMEDIA_TYPE_AUDIO, -1, videoIndex, nil, 0)
        let audioIndex = audioStreamIndex ?? bestAudioIndex
        if audioIndex >= 0, Int(audioIndex) < Int(formatContext!.pointee.nb_streams), let stream = formatContext!.pointee.streams[Int(audioIndex)], stream.pointee.codecpar.pointee.codec_type == AVMEDIA_TYPE_AUDIO {
            audio = Stream(
                index: audioIndex,
                timeBase: stream.pointee.time_base,
                codecId: stream.pointee.codecpar.pointee.codec_id,
                codecpar: stream.pointee.codecpar
            )
        }

        let streamCount = Int(formatContext!.pointee.nb_streams)
        for index in 0..<streamCount {
            guard let stream = formatContext!.pointee.streams[index],
                  let codecpar = stream.pointee.codecpar else { continue }
            guard codecpar.pointee.codec_type == AVMEDIA_TYPE_SUBTITLE else { continue }
            guard Demuxer.isTextSubtitleCodec(codecpar.pointee.codec_id) else { continue }
            subtitles.append(Stream(
                index: Int32(index),
                timeBase: stream.pointee.time_base,
                codecId: codecpar.pointee.codec_id,
                codecpar: codecpar
            ))
        }

        let duration = formatContext!.pointee.duration
        if duration > 0 {
            durationSeconds = Double(duration) / Double(FF.timeBase)
        }
    }

    /// Bitmap subtitle codecs (PGS/DVB/VobSub) decode to images instead of
    /// text and would need a compositor on top of the video layer.
    private static func isTextSubtitleCodec(_ id: AVCodecID) -> Bool {
        switch id {
        case AV_CODEC_ID_SUBRIP,
             AV_CODEC_ID_TEXT,
             AV_CODEC_ID_ASS,
             AV_CODEC_ID_SSA,
             AV_CODEC_ID_WEBVTT,
             AV_CODEC_ID_MOV_TEXT:
            return true
        default:
            return false
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
        let globalTimestamp = Int64(target * Double(FF.timeBase))
        if let stream = video ?? audio {
            let timestamp = av_rescale_q(
                globalTimestamp,
                AVRational(num: 1, den: Int32(FF.timeBase)),
                stream.timeBase
            )
            let oneSecond = av_rescale_q(
                1,
                AVRational(num: 1, den: 1),
                stream.timeBase
            )
            let minTimestamp = timestamp > oneSecond ? timestamp - oneSecond : Int64.min
            let result = avformat_seek_file(
                context,
                stream.index,
                minTimestamp,
                timestamp,
                timestamp,
                FF.seekBackward
            )
            if result >= 0 {
                avformat_flush(context)
                return
            }
        }
        try ffCheck(av_seek_frame(context, -1, globalTimestamp, FF.seekBackward), "av_seek_frame")
        avformat_flush(context)
    }

    func close() {
        cancelToken.cancel()
        if context != nil {
            avformat_close_input(&context)
        }
    }
}
