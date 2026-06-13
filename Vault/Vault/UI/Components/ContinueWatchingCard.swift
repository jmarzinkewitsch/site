import SwiftUI

/// 16:9 card with amber progress bar at the bottom edge,
/// used in the Continue Watching / Next Up shelves.
struct ContinueWatchingCard: View {
    let item: BaseItemDto
    let imageURL: URL?
    var width: CGFloat = Theme.continueCardWidth

    private var progress: Double {
        (item.playedPercentage ?? 0) / 100
    }

    private var title: String {
        item.kind == .episode ? (item.seriesName ?? item.name ?? "—") : (item.name ?? "—")
    }

    var body: some View {
        ZStack(alignment: .bottomLeading) {
            RemoteImage(url: imageURL)
                .frame(width: width, height: width * 9 / 16)

            LinearGradient(
                colors: [.black.opacity(0.85), .clear],
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
        .frame(width: width, height: width * 9 / 16)
        .clipShape(RoundedRectangle(cornerRadius: Theme.cornerRadius))
        .modifier(FocusRing())
    }
}
