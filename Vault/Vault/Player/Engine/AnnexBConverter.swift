import Foundation

/// Fallback for streams whose extradata is Annex B (start codes) instead of
/// avcC/hvcC: converts packet payloads to 4-byte length prefixes and harvests
/// in-band parameter sets to build the format description lazily.
struct AnnexBConverter {
    let isHEVC: Bool
    private(set) var vps: Data?
    private(set) var sps: Data?
    private(set) var pps: Data?

    init(isHEVC: Bool) {
        self.isHEVC = isHEVC
    }

    var hasParameterSets: Bool {
        isHEVC ? (vps != nil && sps != nil && pps != nil) : (sps != nil && pps != nil)
    }

    /// Converts one Annex B packet to length-prefixed format. Parameter-set
    /// NALs are captured and stripped (they live in the format description).
    mutating func convert(data: UnsafePointer<UInt8>, size: Int) -> Data {
        var output = Data(capacity: size + 32)
        let buffer = UnsafeBufferPointer(start: data, count: size)

        // Find all 00 00 01 start-code positions (covers 00 00 00 01 too).
        var starts: [Int] = []
        var index = 0
        while index + 2 < size {
            if buffer[index] == 0, buffer[index + 1] == 0, buffer[index + 2] == 1 {
                starts.append(index + 3)
                index += 3
            } else {
                index += 1
            }
        }

        for (position, nalStart) in starts.enumerated() {
            var nalEnd = position + 1 < starts.count ? starts[position + 1] - 3 : size
            // 4-byte start code: the byte before the next 00 00 01 is a zero
            // that belongs to the start code, not the NAL.
            if nalEnd > nalStart, buffer[nalEnd - 1] == 0 { nalEnd -= 1 }
            let length = nalEnd - nalStart
            guard length > 0 else { continue }

            let nalType = isHEVC ? (buffer[nalStart] >> 1) & 0x3F : buffer[nalStart] & 0x1F
            let nal = Data(bytes: data + nalStart, count: length)

            if isHEVC {
                switch nalType {
                case 32: vps = nal; continue
                case 33: sps = nal; continue
                case 34: pps = nal; continue
                default: break
                }
            } else {
                switch nalType {
                case 7: sps = nal; continue
                case 8: pps = nal; continue
                default: break
                }
            }

            var bigEndianLength = UInt32(length).bigEndian
            withUnsafeBytes(of: &bigEndianLength) { output.append(contentsOf: $0) }
            output.append(nal)
        }
        return output
    }

    func makeFormatInfo() throws -> VideoFormatInfo {
        let sets = [vps, sps, pps].compactMap { $0 }
        let description = try VideoFormatDescFactory.make(
            kind: isHEVC ? .hevc : .h264, parameterSets: sets
        )
        return VideoFormatInfo(formatDescription: description, nalLengthSize: 4)
    }
}
