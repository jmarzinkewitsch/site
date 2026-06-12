import CoreMedia
import Foundation

enum VideoCodecKind {
    case h264
    case hevc
}

struct VideoFormatInfo {
    let formatDescription: CMVideoFormatDescription
    /// NAL length prefix size used in the bitstream (from avcC/hvcC).
    let nalLengthSize: Int
}

/// Builds a CMVideoFormatDescription from avcC (H.264) or hvcC (HEVC)
/// extradata. The format description carries SPS/PPS(/VPS) so that
/// AVSampleBufferDisplayLayer can decode length-prefixed samples directly.
enum VideoFormatDescFactory {
    static func make(kind: VideoCodecKind, extradata: Data) throws -> VideoFormatInfo {
        switch kind {
        case .h264: return try fromAVCC(extradata)
        case .hevc: return try fromHVCC(extradata)
        }
    }

    static func make(kind: VideoCodecKind, parameterSets: [Data]) throws -> CMVideoFormatDescription {
        try createDescription(kind: kind, parameterSets: parameterSets)
    }

    // MARK: - avcC (ISO 14496-15 AVCDecoderConfigurationRecord)

    private static func fromAVCC(_ data: Data) throws -> VideoFormatInfo {
        guard data.count > 6, data[0] == 1 else { throw PlayerError.badExtradata }
        let nalLengthSize = Int(data[4] & 0x03) + 1
        var parameterSets: [Data] = []
        var cursor = 6

        let spsCount = Int(data[5] & 0x1F)
        for _ in 0..<spsCount {
            try appendLengthPrefixedSet(from: data, cursor: &cursor, into: &parameterSets)
        }
        guard cursor < data.count else { throw PlayerError.badExtradata }
        let ppsCount = Int(data[cursor])
        cursor += 1
        for _ in 0..<ppsCount {
            try appendLengthPrefixedSet(from: data, cursor: &cursor, into: &parameterSets)
        }

        let description = try createDescription(kind: .h264, parameterSets: parameterSets)
        return VideoFormatInfo(formatDescription: description, nalLengthSize: nalLengthSize)
    }

    // MARK: - hvcC (ISO 14496-15 HEVCDecoderConfigurationRecord)

    private static func fromHVCC(_ data: Data) throws -> VideoFormatInfo {
        guard data.count > 23, data[0] == 1 else { throw PlayerError.badExtradata }
        let nalLengthSize = Int(data[21] & 0x03) + 1
        let arrayCount = Int(data[22])
        var parameterSets: [Data] = []
        var cursor = 23

        for _ in 0..<arrayCount {
            guard cursor + 3 <= data.count else { throw PlayerError.badExtradata }
            let nalType = data[cursor] & 0x3F
            let naluCount = Int(data[cursor + 1]) << 8 | Int(data[cursor + 2])
            cursor += 3
            for _ in 0..<naluCount {
                guard cursor + 2 <= data.count else { throw PlayerError.badExtradata }
                let length = Int(data[cursor]) << 8 | Int(data[cursor + 1])
                cursor += 2
                guard cursor + length <= data.count else { throw PlayerError.badExtradata }
                // Only VPS (32), SPS (33), PPS (34) — SEI arrays would be rejected.
                if nalType == 32 || nalType == 33 || nalType == 34 {
                    parameterSets.append(data.subdata(in: cursor..<cursor + length))
                }
                cursor += length
            }
        }

        let description = try createDescription(kind: .hevc, parameterSets: parameterSets)
        return VideoFormatInfo(formatDescription: description, nalLengthSize: nalLengthSize)
    }

    // MARK: - Shared

    private static func appendLengthPrefixedSet(
        from data: Data, cursor: inout Int, into sets: inout [Data]
    ) throws {
        guard cursor + 2 <= data.count else { throw PlayerError.badExtradata }
        let length = Int(data[cursor]) << 8 | Int(data[cursor + 1])
        cursor += 2
        guard cursor + length <= data.count else { throw PlayerError.badExtradata }
        sets.append(data.subdata(in: cursor..<cursor + length))
        cursor += length
    }

    private static func createDescription(
        kind: VideoCodecKind, parameterSets: [Data]
    ) throws -> CMVideoFormatDescription {
        guard !parameterSets.isEmpty else { throw PlayerError.badExtradata }

        // Copy parameter sets into stable allocations for the C call.
        let buffers: [UnsafeMutablePointer<UInt8>] = parameterSets.map { set in
            let pointer = UnsafeMutablePointer<UInt8>.allocate(capacity: set.count)
            set.withUnsafeBytes { raw in
                pointer.update(from: raw.bindMemory(to: UInt8.self).baseAddress!, count: set.count)
            }
            return pointer
        }
        defer { buffers.forEach { $0.deallocate() } }

        var pointers: [UnsafePointer<UInt8>] = buffers.map { UnsafePointer($0) }
        var sizes: [Int] = parameterSets.map(\.count)
        var description: CMVideoFormatDescription?
        let status: OSStatus

        switch kind {
        case .h264:
            status = CMVideoFormatDescriptionCreateFromH264ParameterSets(
                allocator: kCFAllocatorDefault,
                parameterSetCount: pointers.count,
                parameterSetPointers: &pointers,
                parameterSetSizes: &sizes,
                nalUnitHeaderLength: 4,
                formatDescriptionOut: &description
            )
        case .hevc:
            status = CMVideoFormatDescriptionCreateFromHEVCParameterSets(
                allocator: kCFAllocatorDefault,
                parameterSetCount: pointers.count,
                parameterSetPointers: &pointers,
                parameterSetSizes: &sizes,
                nalUnitHeaderLength: 4,
                extensions: nil,
                formatDescriptionOut: &description
            )
        }

        guard status == 0, let description else {
            throw PlayerError.formatDescription(status)
        }
        return description
    }
}
