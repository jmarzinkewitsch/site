import SwiftUI

/// Persistent top chrome: a live clock on the right. Purely decorative — the
/// tvOS TabView underneath stays the primary navigation, so this is
/// non-interactive and hidden from VoiceOver to avoid competing for focus.
struct TopBar: View {
    var body: some View {
        HStack {
            Spacer()
            TimelineView(.periodic(from: .now, by: 1)) { context in
                Text(context.date, format: .dateTime.hour().minute())
                    .font(.system(size: 26, weight: .semibold).monospacedDigit())
                    .foregroundStyle(Theme.textDim)
            }
        }
        .padding(.horizontal, Theme.screenPadding)
        .padding(.top, Theme.Spacing.m)
        .ignoresSafeArea(edges: .horizontal)
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }
}
