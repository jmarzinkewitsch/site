import SwiftUI

/// 16:9 card with amber progress bar at the bottom edge,
/// used in the Continue Watching / Next Up shelves.
struct ContinueWatchingCard: View {
    enum ArtworkStyle {
        case backdrop
        case poster
    }

    let item: BaseItemDto
    let imageURL: URL?
    var width: CGFloat = Theme.continueCardWidth
    var artworkStyle: ArtworkStyle = .backdrop

    private var progress: Double {
        item.watchedFraction
    }

    private var title: String {
        item.name ?? "—"
    }

    private var subtitle: String? {
        guard item.kind == .episode else { return nil }
        return [item.seriesName, item.episodeCode].compactMap { $0 }.joined(separator: " · ")
    }

    var body: some View {
        switch artworkStyle {
        case .backdrop:
            backdropBody
        case .poster:
            posterBody
        }
    }

    private var backdropBody: some View {
        ZStack(alignment: .bottomLeading) {
            RemoteImage(url: imageURL)
                .frame(width: width, height: width * Theme.cardAspectRatio)
                .accessibilityHidden(true)

            LinearGradient(
                colors: [.black.opacity(Theme.Opacity.cardScrim), .clear],
                startPoint: .bottom, endPoint: .center
            )

            VStack(alignment: .leading, spacing: 4) {
                if let subtitle {
                    Text(subtitle)
                        .font(.system(size: 16, weight: .medium))
                        .foregroundStyle(Theme.textDim)
                        .lineLimit(1)
                }
                Text(title)
                    .font(.system(size: 21, weight: .semibold))
                    .lineLimit(1)
                    .foregroundStyle(Theme.textPrimary)
            }
            .padding(.horizontal, 16)
            .padding(.bottom, 16)

            if progress > 0 {
                GeometryReader { geo in
                    Rectangle()
                        .fill(Theme.accent)
                        .frame(width: geo.size.width * progress, height: 6)
                        .frame(maxHeight: .infinity, alignment: .bottom)
                }
            }
        }
        .frame(width: width, height: width * Theme.cardAspectRatio)
        .clipShape(RoundedRectangle(cornerRadius: Theme.cornerRadius))
        .modifier(FocusRing())
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(accessibilityLabel)
    }

    private var posterBody: some View {
        VStack(alignment: .leading, spacing: 12) {
            ZStack(alignment: .bottomLeading) {
                RemoteImage(url: imageURL)
                    .frame(width: width, height: width * Theme.posterAspectRatio)
                    .accessibilityHidden(true)

                if progress > 0 {
                    GeometryReader { geo in
                        Rectangle()
                            .fill(Theme.accent)
                            .frame(width: geo.size.width * progress, height: 6)
                            .frame(maxHeight: .infinity, alignment: .bottom)
                    }
                }
            }
            .frame(width: width, height: width * Theme.posterAspectRatio)
            .clipShape(RoundedRectangle(cornerRadius: Theme.cornerRadius))
            .modifier(FocusRing())

            VStack(alignment: .leading, spacing: 3) {
                if let subtitle {
                    Text(subtitle)
                        .font(.system(size: 16, weight: .medium))
                        .lineLimit(1)
                        .foregroundStyle(Theme.textDim)
                }
                Text(title)
                    .font(.system(size: 21, weight: .semibold))
                    .lineLimit(2)
                    .foregroundStyle(Theme.textPrimary)
            }
            .frame(width: width, alignment: .leading)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(accessibilityLabel)
    }

    private var accessibilityLabel: String {
        var parts = [title]
        if let subtitle { parts.append(subtitle) }
        if progress > 0 { parts.append("\(Int(progress * 100)) Prozent gesehen") }
        return parts.joined(separator: ", ")
    }
}
