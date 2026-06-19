import SwiftUI

/// Horizontal shelf with a section title.
struct MediaShelf<Content: View>: View {
    let title: String
    @ViewBuilder let content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            Text(title)
                .font(.system(size: 32, weight: .bold))
                .foregroundStyle(Theme.textPrimary)
                .padding(.leading, Theme.screenPadding)
            ScrollView(.horizontal, showsIndicators: false) {
                LazyHStack(alignment: .top, spacing: 32) {
                    content
                }
                .padding(.horizontal, Theme.screenPadding)
                .padding(.top, Theme.shelfFocusPadding)
                .padding(.bottom, Theme.shelfFocusPadding + 10)
            }
            .scrollClipDisabled()
        }
    }
}
