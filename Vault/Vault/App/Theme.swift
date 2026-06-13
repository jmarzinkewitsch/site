import SwiftUI

enum Theme {
    // Colors
    static let bg = Color(red: 10 / 255, green: 10 / 255, blue: 12 / 255)          // #0A0A0C
    static let accent = Color(red: 232 / 255, green: 160 / 255, blue: 48 / 255)    // #E8A030
    static let surface = Color(red: 22 / 255, green: 22 / 255, blue: 26 / 255)     // #16161A
    static let textPrimary = Color(red: 242 / 255, green: 242 / 255, blue: 244 / 255)
    static let textDim = Color(red: 154 / 255, green: 154 / 255, blue: 160 / 255)
    static let accentText = Color(red: 26 / 255, green: 18 / 255, blue: 6 / 255)   // dark text on amber

    // Metrics (1920×1080 pt canvas, 10-foot UI)
    static let posterWidth: CGFloat = 204
    static let continueCardWidth: CGFloat = 365
    static let cornerRadius: CGFloat = 14
    static let screenPadding: CGFloat = 90
    static let stageHeight: CGFloat = 620
}

enum Format {
    /// 9960 s → "2 Std. 46 Min."
    static func runtime(seconds: Double) -> String {
        let total = Int(seconds.rounded())
        let hours = total / 3600
        let minutes = (total % 3600) / 60
        if hours > 0 { return "\(hours) Std. \(minutes) Min." }
        return "\(minutes) Min."
    }

    /// 4332 s → "1:12:12"; 754 s → "12:34"
    static func clock(seconds: Double) -> String {
        let total = max(0, Int(seconds.rounded()))
        let hours = total / 3600
        let minutes = (total % 3600) / 60
        let secs = total % 60
        if hours > 0 { return String(format: "%d:%02d:%02d", hours, minutes, secs) }
        return String(format: "%d:%02d", minutes, secs)
    }

    /// Codec badges like ["4K", "HEVC", "EAC3 5.1"] from media streams.
    static func badges(for streams: [MediaStream]) -> [String] {
        var result: [String] = []
        if let video = streams.first(where: { $0.type == "Video" }) {
            if let height = video.height, height >= 2000 { result.append("4K") }
            if let codec = video.codec { result.append(codec.uppercased()) }
            if let range = video.videoRange, range.uppercased() != "SDR" { result.append(range.uppercased()) }
        }
        if let audio = streams.first(where: { $0.type == "Audio" }) {
            var label = audio.codec?.uppercased() ?? ""
            if let channels = audio.channels {
                switch channels {
                case 1: label += " 1.0"
                case 2: label += " 2.0"
                case 6: label += " 5.1"
                case 8: label += " 7.1"
                default: label += " \(channels)ch"
                }
            }
            if !label.isEmpty { result.append(label.trimmingCharacters(in: .whitespaces)) }
        }
        return result
    }
}
