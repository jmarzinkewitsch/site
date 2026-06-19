import Foundation
import OSLog

/// Downloads and parses an external subtitle sidecar (SRT/WebVTT) into
/// SubtitleCues. Used for subs that aren't muxed into the direct stream —
/// e.g. files added by Jellyfin's OpenSubtitles plugin, delivered by the
/// server as `.../Subtitles/{index}/0/Stream.srt`.
enum ExternalSubtitleLoader {
    private static let logger = Logger(subsystem: "vault.player", category: "subtitles")

    static func load(from url: URL, headers: [String: String]) async -> [SubtitleCue] {
        var request = URLRequest(url: url)
        for (field, value) in headers { request.setValue(value, forHTTPHeaderField: field) }
        do {
            let (data, response) = try await URLSession.shared.data(for: request)
            if let http = response as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
                logger.error("Subtitle download failed: HTTP \(http.statusCode, privacy: .public)")
                return []
            }
            let text = String(decoding: data, as: UTF8.self)
            return SubtitleSidecarParser.parse(text)
        } catch {
            logger.error("Subtitle download error: \(error.localizedDescription, privacy: .public)")
            return []
        }
    }
}

/// Parses SRT and WebVTT cue blocks. Both share the same block structure
/// (`timing` line + text), differing mainly in the millisecond separator
/// (`,` vs `.`) and an optional `WEBVTT` header / cue identifiers.
enum SubtitleSidecarParser {
    static func parse(_ raw: String) -> [SubtitleCue] {
        let normalized = raw
            .replacingOccurrences(of: "\r\n", with: "\n")
            .replacingOccurrences(of: "\r", with: "\n")
        var cues: [SubtitleCue] = []
        for block in normalized.components(separatedBy: "\n\n") {
            var lines = block.split(separator: "\n", omittingEmptySubsequences: false).map(String.init)
            // Drop leading blank lines that survive the split.
            while let first = lines.first, first.trimmingCharacters(in: .whitespaces).isEmpty {
                lines.removeFirst()
            }
            guard let head = lines.first else { continue }
            // Skip WebVTT header and metadata blocks.
            if head.hasPrefix("WEBVTT") || head.hasPrefix("NOTE") || head.hasPrefix("STYLE") { continue }
            // SRT sequence number or VTT cue identifier: a non-timing first line.
            if !head.contains("-->"), lines.count > 1 { lines.removeFirst() }
            guard let timing = lines.first, timing.contains("-->"),
                  let (start, end) = parseTiming(timing) else { continue }
            let text = lines.dropFirst()
                .joined(separator: "\n")
                .trimmingCharacters(in: .whitespacesAndNewlines)
            let clean = stripTags(text)
            guard !clean.isEmpty else { continue }
            cues.append(SubtitleCue(startSeconds: start, endSeconds: max(end, start + 0.5), text: clean))
        }
        return cues
    }

    /// `00:01:02,500 --> 00:01:05,000` (SRT) or
    /// `00:01:02.500 --> 00:01:05.000 line:90%` (VTT, trailing cue settings).
    private static func parseTiming(_ line: String) -> (Double, Double)? {
        let parts = line.components(separatedBy: "-->")
        guard parts.count == 2,
              let start = seconds(from: parts[0]),
              let end = seconds(from: parts[1]) else { return nil }
        return (start, end)
    }

    private static func seconds(from raw: String) -> Double? {
        // First whitespace-separated token drops any VTT cue settings.
        let token = raw.trimmingCharacters(in: .whitespaces)
            .split(separator: " ").first.map(String.init) ?? ""
        let normalized = token.replacingOccurrences(of: ",", with: ".")
        let components = normalized.split(separator: ":")
        guard !components.isEmpty else { return nil }
        var total = 0.0
        for component in components {
            guard let value = Double(component) else { return nil }
            total = total * 60 + value
        }
        return total
    }

    /// Strips HTML-ish tags (`<i>`, `<b>`, `<font …>`) and ASS override
    /// blocks (`{…}`) that some sidecars carry.
    private static func stripTags(_ input: String) -> String {
        var output = ""
        output.reserveCapacity(input.count)
        var skipDepth = 0
        for ch in input {
            switch ch {
            case "<", "{": skipDepth += 1
            case ">", "}": if skipDepth > 0 { skipDepth -= 1 }
            default: if skipDepth == 0 { output.append(ch) }
            }
        }
        return output.trimmingCharacters(in: .whitespacesAndNewlines)
    }
}
