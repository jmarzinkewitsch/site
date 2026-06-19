import SwiftUI
import ImageIO
import CoreGraphics
import OSLog

/// Thread-safe actor that samples the dominant colour from a backdrop URL
/// and returns a nudged ``SwiftUI/Color`` suitable for ambient-lighting use.
/// Results are cached so repeated focus changes cost nothing after the first
/// load for each image.
actor AmbientColorProvider {
    static let shared = AmbientColorProvider()

    private let logger = Logger(subsystem: "de.marzinkewitsch.Vault", category: "AmbientColor")
    private var cache: [URL: Color] = [:]

    /// Returns the ambient `Color` derived from the image at `url`, or `nil`
    /// if the image could not be fetched or sampled.
    func color(for url: URL) async -> Color? {
        if let cached = cache[url] { return cached }
        guard let result = await sample(url: url) else { return nil }
        cache[url] = result
        return result
    }

    // MARK: – Private

    private func sample(url: URL) async -> Color? {
        do {
            let (data, _) = try await URLSession.shared.data(from: url)
            return extractColor(from: data)
        } catch {
            logger.warning("AmbientColor: failed to fetch \(url.absoluteString, privacy: .public): \(error.localizedDescription, privacy: .public)")
            return nil
        }
    }

    private func extractColor(from data: Data) -> Color? {
        guard let source = CGImageSourceCreateWithData(data as CFData, nil) else {
            logger.warning("AmbientColor: CGImageSourceCreateWithData returned nil")
            return nil
        }

        // Create a tiny 16×16 thumbnail — enough to get the dominant hue cheaply.
        let thumbnailOptions: [CFString: Any] = [
            kCGImageSourceThumbnailMaxPixelSize: 16,
            kCGImageSourceCreateThumbnailFromImageAlways: true,
            kCGImageSourceCreateThumbnailWithTransform: true
        ]
        guard let thumbnail = CGImageSourceCreateThumbnailAtIndex(source, 0, thumbnailOptions as CFDictionary) else {
            logger.warning("AmbientColor: thumbnail creation failed")
            return nil
        }

        // Render into a 1×1 RGBA context to average all pixels in one step.
        let colorSpace = CGColorSpaceCreateDeviceRGB()
        var pixelData: [UInt8] = [0, 0, 0, 255]
        guard let ctx = CGContext(
            data: &pixelData,
            width: 1,
            height: 1,
            bitsPerComponent: 8,
            bytesPerRow: 4,
            space: colorSpace,
            bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
        ) else {
            logger.warning("AmbientColor: CGContext creation failed")
            return nil
        }

        ctx.draw(thumbnail, in: CGRect(x: 0, y: 0, width: 1, height: 1))

        // pixelData is now [R, G, B, A] as premultiplied bytes.
        let alpha = CGFloat(pixelData[3]) / 255
        guard alpha > 0 else { return nil }
        let r = CGFloat(pixelData[0]) / 255 / alpha
        let g = CGFloat(pixelData[1]) / 255 / alpha
        let b = CGFloat(pixelData[2]) / 255 / alpha

        // Convert to HSB and nudge toward a pleasant mid-brightness glow:
        // – clamp brightness to 0.5–0.65 so it isn't too dark or blown-out
        // – boost saturation to at least 0.4 so grey backdrops still tint
        var hue: CGFloat = 0
        var saturation: CGFloat = 0
        var brightness: CGFloat = 0
        UIColor(red: r, green: g, blue: b, alpha: 1).getHue(&hue, saturation: &saturation, brightness: &brightness, alpha: nil)

        let clampedBrightness = min(0.65, max(0.5, brightness))
        let boostedSaturation = max(saturation, 0.4)

        return Color(hue: hue, saturation: boostedSaturation, brightness: clampedBrightness)
    }
}
