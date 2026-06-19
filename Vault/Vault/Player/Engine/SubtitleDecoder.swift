import Foundation
import Libavcodec
import Libavformat
import Libavutil

/// Decodes text-based subtitle packets (SRT/ASS/SSA/WebVTT/MOV_TEXT) into
/// SubtitleCues. Driven from the demux thread — not thread-safe.
///
/// Bitmap subtitles (PGS/DVB/DVD-VobSub) are intentionally not handled here:
/// rendering them would require a CoreGraphics pipeline on top of the video
/// layer.
final class SubtitleDecoder {
    private var codecContext: UnsafeMutablePointer<AVCodecContext>?
    private let timeBase: AVRational

    init(stream: Demuxer.Stream) throws {
        timeBase = stream.timeBase
        guard let codec = avcodec_find_decoder(stream.codecpar.pointee.codec_id) else {
            throw PlayerError.unsupportedCodec("Subtitle-Codec-ID \(stream.codecpar.pointee.codec_id.rawValue)")
        }
        guard let context = avcodec_alloc_context3(codec) else {
            throw PlayerError.openFailed("alloc subtitle codec context")
        }
        codecContext = context
        try ffCheck(avcodec_parameters_to_context(context, stream.codecpar), "subtitle parameters_to_context")
        try ffCheck(avcodec_open2(context, codec, nil), "avcodec_open2 subtitle")
    }

    deinit {
        if codecContext != nil { avcodec_free_context(&codecContext) }
    }

    /// Decodes one packet, returning zero or more cues. The packet stays
    /// owned by the caller.
    func decode(packet: UnsafeMutablePointer<AVPacket>) -> [SubtitleCue] {
        guard let context = codecContext else { return [] }
        var subtitle = AVSubtitle()
        var got: Int32 = 0
        let result = avcodec_decode_subtitle2(context, &subtitle, &got, packet)
        guard result >= 0, got != 0 else {
            if got != 0 { avsubtitle_free(&subtitle) }
            return []
        }
        defer { avsubtitle_free(&subtitle) }

        let basePts = ffSeconds(packet.pointee.pts, timeBase: timeBase) ?? 0
        let packetDuration = ffSeconds(packet.pointee.duration, timeBase: timeBase)
        let startOffset = Double(subtitle.start_display_time) / 1000.0
        let endRaw = subtitle.end_display_time

        var cues: [SubtitleCue] = []
        for index in 0..<Int(subtitle.num_rects) {
            guard let rectPointer = subtitle.rects?[index] else { continue }
            let rect = rectPointer.pointee
            var raw: String?
            switch rect.type {
            case SUBTITLE_TEXT:
                if let cStr = rect.text { raw = String(cString: cStr) }
            case SUBTITLE_ASS:
                if let cStr = rect.ass { raw = SubtitleDecoder.parseAssEvent(String(cString: cStr)) }
            default:
                continue
            }
            guard let text = raw?.trimmingCharacters(in: .whitespacesAndNewlines), !text.isEmpty else { continue }

            let start = basePts + startOffset
            let end: Double
            if endRaw == UInt32.max || endRaw == 0 {
                end = start + max(packetDuration ?? 4.0, 0.5)
            } else {
                end = basePts + Double(endRaw) / 1000.0
            }
            cues.append(SubtitleCue(startSeconds: start, endSeconds: max(end, start + 0.5), text: text))
        }
        return cues
    }

    func flush() {
        if let context = codecContext { avcodec_flush_buffers(context) }
    }

    /// libav emits ASS events in the form
    /// `ReadOrder,Layer,Style,Name,MarginL,MarginR,MarginV,Effect,Text`
    /// (9 fields, 8 commas before the text). The text itself may contain
    /// override blocks `{...}` and ASS-specific escapes (`\N`, `\h`).
    static func parseAssEvent(_ line: String) -> String {
        let parts = line.split(separator: ",", maxSplits: 8, omittingEmptySubsequences: false)
        let textField = parts.count >= 9 ? String(parts[8]) : line
        return stripAssTags(textField)
    }

    private static func stripAssTags(_ input: String) -> String {
        var output = ""
        output.reserveCapacity(input.count)
        var iterator = input.makeIterator()
        var inTag = false
        while let ch = iterator.next() {
            if ch == "{" { inTag = true; continue }
            if ch == "}" { inTag = false; continue }
            if inTag { continue }
            if ch == "\\" {
                if let next = iterator.next() {
                    switch next {
                    case "N", "n": output.append("\n")
                    case "h": output.append(" ")
                    default:
                        output.append("\\")
                        output.append(next)
                    }
                }
                continue
            }
            output.append(ch)
        }
        return output
    }
}
