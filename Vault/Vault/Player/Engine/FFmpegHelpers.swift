import CoreMedia
import Foundation
import Libavcodec
import Libavformat
import Libavutil

/// FFmpeg constants that are C macros and therefore not imported into Swift.
enum FF {
    /// AVERROR_EOF = FFERRTAG('E','O','F',' ')
    static let eof: Int32 = -541_478_725
    /// AVERROR(EAGAIN) — EAGAIN is 35 on Darwin
    static let eagain: Int32 = -35
    /// AV_NOPTS_VALUE
    static let noPTS = Int64(bitPattern: 0x8000_0000_0000_0000)
    /// AV_TIME_BASE
    static let timeBase: Int64 = 1_000_000
    /// AVSEEK_FLAG_BACKWARD
    static let seekBackward: Int32 = 1
    /// AV_PKT_FLAG_KEY
    static let pktFlagKey: Int32 = 1

    static func errorString(_ code: Int32) -> String {
        var buffer = [CChar](repeating: 0, count: 256)
        av_strerror(code, &buffer, 256)
        return String(cString: buffer)
    }
}

struct FFmpegError: Error {
    let code: Int32
    let context: String
    var message: String { "\(context): \(FF.errorString(code)) (\(code))" }
}

@inline(__always)
func ffCheck(_ code: Int32, _ context: String) throws {
    if code < 0 { throw FFmpegError(code: code, context: context) }
}

enum PlayerError: Error {
    case badExtradata
    case formatDescription(OSStatus)
    case sampleBuffer(OSStatus)
    case unsupportedCodec(String)
    case audioSetup(String)
    case openFailed(String)

    var message: String {
        switch self {
        case .badExtradata: return "Codec-Extradata nicht lesbar"
        case .formatDescription(let status): return "FormatDescription fehlgeschlagen (\(status))"
        case .sampleBuffer(let status): return "SampleBuffer fehlgeschlagen (\(status))"
        case .unsupportedCodec(let name): return "Codec nicht unterstützt: \(name)"
        case .audioSetup(let detail): return "Audio-Setup fehlgeschlagen: \(detail)"
        case .openFailed(let detail): return "Stream konnte nicht geöffnet werden: \(detail)"
        }
    }
}

extension AVRational {
    var doubleValue: Double { den == 0 ? 0 : Double(num) / Double(den) }
}

/// Stream timestamp → CMTime (90 kHz), .invalid for AV_NOPTS_VALUE.
func ffCMTime(_ value: Int64, timeBase: AVRational) -> CMTime {
    guard value != FF.noPTS else { return .invalid }
    let rescaled = av_rescale_q(value, timeBase, AVRational(num: 1, den: 90000))
    return CMTime(value: rescaled, timescale: 90000)
}

func ffSeconds(_ value: Int64, timeBase: AVRational) -> Double? {
    value == FF.noPTS ? nil : Double(value) * timeBase.doubleValue
}

/// Tiny lock-protected value box for flags shared across player threads.
final class AtomicValue<T> {
    private var value: T
    private let lock = NSLock()

    init(_ value: T) { self.value = value }

    func get() -> T {
        lock.lock(); defer { lock.unlock() }
        return value
    }

    func set(_ newValue: T) {
        lock.lock(); defer { lock.unlock() }
        value = newValue
    }

    /// Returns the old value.
    @discardableResult
    func exchange(_ newValue: T) -> T {
        lock.lock(); defer { lock.unlock() }
        let old = value
        value = newValue
        return old
    }
}
