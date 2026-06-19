import Foundation
import ImageIO
import OSLog

/// Downloads and crops trickplay tile sheets into individual thumbnail CGImages
/// for a given playback position.
///
/// Tile sheets are cached by sheet-index (capped to `maxCachedSheets`) so
/// repeated scrubs over the same time range avoid redundant network requests.
/// The actor itself serialises all access; callers may `await` from any
/// concurrency domain.
actor TrickplayImageProvider {

    // MARK: - Public API

    init(info: TrickplayInfo, headers: [String: String]) {
        self.info = info
        self.headers = headers
    }

    /// Returns the thumbnail CGImage that corresponds to `seconds`, or `nil`
    /// if the image data cannot be fetched or cropped.
    func image(atSeconds seconds: Double) async -> CGImage? {
        // --- index maths ---------------------------------------------------
        let thumbIndex: Int = {
            let raw = Int((seconds * 1000.0) / Double(info.interval))
            return max(0, min(raw, info.thumbnailCount - 1))
        }()

        let perSheet   = info.tileWidth * info.tileHeight
        let sheetIndex = thumbIndex / perSheet
        let posInSheet = thumbIndex % perSheet
        let row        = posInSheet / info.tileWidth
        let col        = posInSheet % info.tileWidth

        let cropRect = CGRect(
            x: col * info.thumbnailWidth,
            y: row * info.thumbnailHeight,
            width: info.thumbnailWidth,
            height: info.thumbnailHeight
        )

        // --- sheet download / cache ----------------------------------------
        let sheet: CGImage
        if let cached = cache[sheetIndex] {
            sheet = cached
        } else {
            guard let downloaded = await fetchSheet(index: sheetIndex) else { return nil }
            evictIfNeeded()
            cache[sheetIndex] = downloaded
            cacheOrder.append(sheetIndex)
            sheet = downloaded
        }

        // --- crop ----------------------------------------------------------
        guard let cropped = sheet.cropping(to: cropRect) else {
            Self.logger.error("Trickplay crop failed: sheet \(sheetIndex, privacy: .public) row \(row, privacy: .public) col \(col, privacy: .public)")
            return nil
        }
        return cropped
    }

    // MARK: - Private

    private static let logger = Logger(subsystem: "vault.player", category: "trickplay")
    private let info: TrickplayInfo
    private let headers: [String: String]

    /// Decoded CGImages keyed by sheet index.
    private var cache: [Int: CGImage] = [:]
    /// Insertion order so we can evict the oldest sheet when the cap is reached.
    private var cacheOrder: [Int] = []
    private let maxCachedSheets = 8

    private func evictIfNeeded() {
        guard cache.count >= maxCachedSheets else { return }
        let oldest = cacheOrder.removeFirst()
        cache.removeValue(forKey: oldest)
    }

    /// Fetches one tile sheet and decodes it into a CGImage. Returns `nil` on
    /// any network or decoding failure — never throws; caller receives `nil`.
    private func fetchSheet(index: Int) async -> CGImage? {
        let urlString = info.tileURLTemplate.replacingOccurrences(of: "{index}", with: String(index))
        guard let url = URL(string: urlString) else {
            Self.logger.error("Trickplay invalid sheet URL: \(urlString, privacy: .public)")
            return nil
        }

        var request = URLRequest(url: url, timeoutInterval: 10)
        for (field, value) in headers {
            request.setValue(value, forHTTPHeaderField: field)
        }

        let data: Data
        do {
            let (raw, response) = try await URLSession.shared.data(for: request)
            if let http = response as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
                Self.logger.error("Trickplay sheet HTTP \(http.statusCode, privacy: .public) for index \(index)")
                return nil
            }
            data = raw
        } catch {
            Self.logger.error("Trickplay sheet download error: \(error.localizedDescription, privacy: .public)")
            return nil
        }

        return cgImage(from: data)
    }

    /// Decodes raw JPEG (or any ImageIO-supported format) bytes into a CGImage.
    private func cgImage(from data: Data) -> CGImage? {
        let cfData = data as CFData
        guard let source = CGImageSourceCreateWithData(cfData, nil) else {
            Self.logger.error("Trickplay: CGImageSourceCreateWithData returned nil")
            return nil
        }
        guard let image = CGImageSourceCreateImageAtIndex(source, 0, nil) else {
            Self.logger.error("Trickplay: CGImageSourceCreateImageAtIndex returned nil")
            return nil
        }
        return image
    }
}
