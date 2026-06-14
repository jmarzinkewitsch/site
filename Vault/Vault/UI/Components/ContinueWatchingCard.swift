import SwiftUI

/// 16:9 card with amber progress bar at the bottom edge,
/// used in the Continue Watching / Next Up shelves.
struct ContinueWatchingCard: View {
    let item: BaseItemDto
    let imageURL: URL?
    var width: CGFloat = Theme.continueCardWidth

    private var progress: Double {
        item.watchedFraction
    }

    private var title: String {
        item.kind == .episode ? (item.seriesName ?? item.name ?? "—") : (item.name ?? "—")
    }

    var body: some View {
        ZStack(alignment: .bottomLeading) {
            RemoteImage(url: imageURL)
                .frame(width: width, height: width * Theme.cardAspectRatio)
                .accessibilityHidden(true)

            LinearGradient(
                colors: [.black.opacity(Theme.Opacity.cardScrim), .clear],
                startPoint: .bottom, endPoint: .center
            )

            VStack(alignment: .leading, spacing: 4) {
                if let code = item.episodeCode {
                    Text(code)
                        .font(.system(size: 16, weight: .medium))
                        .foregroundStyle(Theme.textDim)
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

    private var accessibilityLabel: String {
        var parts = [title]
        if let code = item.episodeCode { parts.append(code) }
        if progress > 0 { parts.append("\(Int(progress * 100)) Prozent gesehen") }
        return parts.joined(separator: ", ")
    }
}
