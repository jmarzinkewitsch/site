import SwiftUI

/// Placeholder shelf shown while content loads: a title bar plus a row of
/// card-shaped blocks that gently pulse, matching the mockup's loading state.
struct SkeletonShelf: View {
    /// Poster shelves use the 2:3 card; Continue/Next Up use the 16:9 card.
    var posterStyle: Bool = true
    @State private var dim = false

    private var cardWidth: CGFloat { posterStyle ? Theme.posterWidth : Theme.continueCardWidth }
    private var cardHeight: CGFloat {
        posterStyle ? cardWidth * Theme.posterAspectRatio : cardWidth * Theme.cardAspectRatio
    }

    var body: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.m) {
            RoundedRectangle(cornerRadius: 6)
                .fill(Theme.surface)
                .frame(width: 280, height: 30)
                .padding(.leading, Theme.screenPadding)

            HStack(spacing: Theme.Spacing.l) {
                ForEach(0..<6, id: \.self) { _ in
                    RoundedRectangle(cornerRadius: Theme.cornerRadius)
                        .fill(Theme.surface)
                        .frame(width: cardWidth, height: cardHeight)
                }
            }
            .padding(.horizontal, Theme.screenPadding)
        }
        .opacity(dim ? 0.4 : 0.85)
        .animation(.easeInOut(duration: 0.9).repeatForever(autoreverses: true), value: dim)
        .onAppear { dim = true }
        .accessibilityHidden(true)
    }
}
