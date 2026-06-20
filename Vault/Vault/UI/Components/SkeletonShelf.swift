import SwiftUI

/// Placeholder shelf shown while content loads: a title bar plus a row of
/// card-shaped blocks with a sweeping shimmer — premium-dark, not flat grey.
struct SkeletonShelf: View {
    /// Poster shelves use the 2:3 card; Continue/Next Up use the 16:9 card.
    var posterStyle: Bool = true

    private var cardWidth: CGFloat { posterStyle ? Theme.posterWidth : Theme.continueCardWidth }
    private var cardHeight: CGFloat {
        posterStyle ? cardWidth * Theme.posterAspectRatio : cardWidth * Theme.cardAspectRatio
    }

    var body: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.m) {
            RoundedRectangle(cornerRadius: 6)
                .fill(Color.white.opacity(0.06))
                .frame(width: 280, height: 30)
                .shimmering()
                .padding(.leading, Theme.screenPadding)

            HStack(spacing: Theme.Spacing.l) {
                ForEach(0..<6, id: \.self) { _ in
                    RoundedRectangle(cornerRadius: Theme.cornerRadius)
                        .fill(Color.white.opacity(0.06))
                        .frame(width: cardWidth, height: cardHeight)
                        .shimmering()
                }
            }
            .padding(.horizontal, Theme.screenPadding)
        }
        .accessibilityHidden(true)
    }
}
