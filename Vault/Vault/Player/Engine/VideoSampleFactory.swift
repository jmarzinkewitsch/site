import CoreMedia
import Foundation
import Libavcodec
import Libavutil

/// Converts demuxed compressed AVPackets (H.264/HEVC) into CMSampleBuffers
/// for AVSampleBufferDisplayLayer. No software decoding happens here —
/// VideoToolbox hardware decode is implicit in the display layer.
final class VideoSampleFactory {
    private enum Mode {
        case lengthPrefixed(nalLengthSize: Int)
        case annexB
    }

    private(set) var formatDescription: CMVideoFormatDescription?
    private var mode: Mode
    private var annexB: AnnexBConverter?
    private let timeBase: AVRational
    let isHEVC: Bool

    init(stream: Demuxer.Stream) throws {
        isHEVC = stream.codecId == AV_CODEC_ID_HEVC
        timeBase = stream.timeBase
        let par = stream.codecpar.pointee
        if let extradata = par.extradata, par.extradata_size > 0, extradata[0] == 1 {
            // avcC / hvcC config record
            let data = Data(bytes: extradata, count: Int(par.extradata_size))
            let info = try VideoFormatDescFactory.make(kind: isHEVC ? .hevc : .h264, extradata: data)
            formatDescription = info.formatDescription
            mode = .lengthPrefixed(nalLengthSize: info.nalLengthSize)
        } else {
            // Annex B (or missing) extradata: harvest parameter sets in-band.
            mode = .annexB
            annexB = AnnexBConverter(isHEVC: isHEVC)
        }
    }

    /// Returns nil for packets that can't be converted yet (e.g. Annex B
    /// before the first parameter sets) — callers just skip those.
    func makeSampleBuffer(packet: UnsafeMutablePointer<AVPacket>) throws -> CMSampleBuffer? {
        let raw = packet.pointee
        guard let dataPointer = raw.data, raw.size > 0 else { return nil }

        let payload: Data
        switch mode {
        case .annexB:
            payload = annexB!.convert(data: dataPointer, size: Int(raw.size))
            if formatDescription == nil {
                guard annexB!.hasParameterSets else { return nil }
                formatDescription = try annexB!.makeFormatInfo().formatDescription
            }
            if payload.isEmpty { return nil }
        case .lengthPrefixed(let nalLengthSize):
            if nalLengthSize == 4 {
                payload = Data(bytes: dataPointer, count: Int(raw.size))
            } else {
                payload = Self.rewriteNALLengths(dataPointer, size: Int(raw.size), from: nalLengthSize)
            }
        }

        guard let formatDescription else { return nil }

        // Copy payload into a CMBlockBuffer
        var blockBuffer: CMBlockBuffer?
        var status = CMBlockBufferCreateWithMemoryBlock(
            allocator: kCFAllocatorDefault,
            memoryBlock: nil,
            blockLength: payload.count,
            blockAllocator: kCFAllocatorDefault,
            customBlockSource: nil,
            offsetToData: 0,
            dataLength: payload.count,
            flags: kCMBlockBufferAssureMemoryNowFlag,
            blockBufferOut: &blockBuffer
        )
        guard status == kCMBlockBufferNoErr, let block = blockBuffer else {
            throw PlayerError.sampleBuffer(status)
        }
        status = payload.withUnsafeBytes { rawBuffer in
            CMBlockBufferReplaceDataBytes(
                with: rawBuffer.baseAddress!,
                blockBuffer: block,
                offsetIntoDestination: 0,
                dataLength: payload.count
            )
        }
        guard status == kCMBlockBufferNoErr else { throw PlayerError.sampleBuffer(status) }

        // Timing: keep decode order (DTS) so the layer reorders B-frames itself.
        let pts = raw.pts != FF.noPTS ? raw.pts : raw.dts
        var timing = CMSampleTimingInfo(
            duration: raw.duration > 0 ? ffCMTime(raw.duration, timeBase: timeBase) : .invalid,
            presentationTimeStamp: ffCMTime(pts, timeBase: timeBase),
            decodeTimeStamp: ffCMTime(raw.dts, timeBase: timeBase)
        )
        var sampleSize = payload.count
        var sampleBuffer: CMSampleBuffer?
        status = CMSampleBufferCreateReady(
            allocator: kCFAllocatorDefault,
            dataBuffer: block,
            formatDescription: formatDescription,
            sampleCount: 1,
            sampleTimingEntryCount: 1,
            sampleTimingArray: &timing,
            sampleSizeEntryCount: 1,
            sampleSizeArray: &sampleSize,
            sampleBufferOut: &sampleBuffer
        )
        guard status == 0, let sample = sampleBuffer else {
            throw PlayerError.sampleBuffer(status)
        }

        if raw.flags & FF.pktFlagKey == 0,
           let attachments = CMSampleBufferGetSampleAttachmentsArray(sample, createIfNecessary: true),
           CFArrayGetCount(attachments) > 0 {
            let dict = unsafeBitCast(CFArrayGetValueAtIndex(attachments, 0), to: CFMutableDictionary.self)
            CFDictionarySetValue(
                dict,
                Unmanaged.passUnretained(kCMSampleAttachmentKey_NotSync).toOpaque(),
                Unmanaged.passUnretained(kCFBooleanTrue).toOpaque()
            )
        }
        return sample
    }

    /// Rewrites 1/2/3-byte NAL length prefixes to 4 bytes.
    private static func rewriteNALLengths(
        _ data: UnsafePointer<UInt8>, size: Int, from prefixSize: Int
    ) -> Data {
        var output = Data(capacity: size + 64)
        var cursor = 0
        while cursor + prefixSize <= size {
            var length = 0
            for offset in 0..<prefixSize {
                length = length << 8 | Int(data[cursor + offset])
            }
            cursor += prefixSize
            guard cursor + length <= size else { break }
            var bigEndianLength = UInt32(length).bigEndian
            withUnsafeBytes(of: &bigEndianLength) { output.append(contentsOf: $0) }
            output.append(Data(bytes: data + cursor, count: length))
            cursor += length
        }
        return output
    }
}
