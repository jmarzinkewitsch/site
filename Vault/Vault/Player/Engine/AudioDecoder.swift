import Foundation
import Libavcodec
import Libavutil
import Libswresample

/// Decodes compressed audio (AC3/EAC3/AAC/…) via libavcodec and converts to
/// interleaved stereo Float32 via libswresample (downmixing if needed).
/// Driven from the engine's audio thread — not thread-safe.
final class AudioDecoder {
    private var codecContext: UnsafeMutablePointer<AVCodecContext>?
    private var swrContext: OpaquePointer?
    private var frame: UnsafeMutablePointer<AVFrame>?
    let sampleRate: Double
    private let timeBase: AVRational

    struct DecodedChunk {
        let pts: Double?
        let samples: [Float]   // interleaved stereo
    }

    init(stream: Demuxer.Stream) throws {
        timeBase = stream.timeBase
        guard let codec = avcodec_find_decoder(stream.codecpar.pointee.codec_id) else {
            throw PlayerError.unsupportedCodec("Audio-Codec-ID \(stream.codecpar.pointee.codec_id.rawValue)")
        }
        guard let context = avcodec_alloc_context3(codec) else {
            throw PlayerError.audioSetup("alloc codec context")
        }
        codecContext = context
        try ffCheck(avcodec_parameters_to_context(context, stream.codecpar), "audio parameters_to_context")
        try ffCheck(avcodec_open2(context, codec, nil), "avcodec_open2 audio")

        let inputRate = context.pointee.sample_rate
        guard inputRate > 0 else { throw PlayerError.audioSetup("sample rate 0") }
        sampleRate = Double(inputRate)

        var outLayout = AVChannelLayout()
        av_channel_layout_default(&outLayout, 2)
        var inLayout = context.pointee.ch_layout
        var swr: OpaquePointer?
        try ffCheck(
            swr_alloc_set_opts2(
                &swr,
                &outLayout, AV_SAMPLE_FMT_FLT, inputRate,
                &inLayout, context.pointee.sample_fmt, inputRate,
                0, nil
            ),
            "swr_alloc_set_opts2"
        )
        try ffCheck(swr_init(swr), "swr_init")
        swrContext = swr
        frame = av_frame_alloc()
    }

    deinit {
        if frame != nil { av_frame_free(&frame) }
        if swrContext != nil { swr_free(&swrContext) }
        if codecContext != nil { avcodec_free_context(&codecContext) }
    }

    /// Sends one packet and drains all resulting frames.
    func decode(packet: UnsafeMutablePointer<AVPacket>) -> [DecodedChunk] {
        guard let context = codecContext, let frame, let swr = swrContext else { return [] }

        let sendResult = avcodec_send_packet(context, packet)
        guard sendResult >= 0 || sendResult == FF.eagain else { return [] }

        var chunks: [DecodedChunk] = []
        while true {
            let result = avcodec_receive_frame(context, frame)
            if result == FF.eagain || result == FF.eof { break }
            guard result >= 0 else { break }

            let frameSamples = Int(frame.pointee.nb_samples)
            guard frameSamples > 0 else { continue }
            var samples = [Float](repeating: 0, count: frameSamples * 2)
            let converted = samples.withUnsafeMutableBytes { rawOutput -> Int32 in
                var outputPointer: UnsafeMutablePointer<UInt8>? =
                    rawOutput.baseAddress!.assumingMemoryBound(to: UInt8.self)
                let inputPointers = UnsafeMutableRawPointer(frame.pointee.extended_data)
                    .assumingMemoryBound(to: UnsafePointer<UInt8>?.self)
                return withUnsafeMutablePointer(to: &outputPointer) { outputArray in
                    swr_convert(swr, outputArray, Int32(frameSamples), inputPointers, Int32(frameSamples))
                }
            }
            guard converted > 0 else { continue }
            if Int(converted) < frameSamples {
                samples.removeLast((frameSamples - Int(converted)) * 2)
            }

            let bestEffort = frame.pointee.best_effort_timestamp
            chunks.append(DecodedChunk(
                pts: ffSeconds(bestEffort, timeBase: timeBase),
                samples: samples
            ))
        }
        return chunks
    }

    /// Drops decoder-internal state after a seek.
    func flush() {
        if let context = codecContext {
            avcodec_flush_buffers(context)
        }
    }
}
