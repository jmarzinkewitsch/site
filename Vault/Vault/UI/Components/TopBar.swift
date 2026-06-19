import SwiftUI

/// Persistent top chrome from the mockup: the VAULT wordmark on the left and a
/// live clock on the right. Purely decorative — the tvOS TabView underneath
/// stays the primary navigation, so this is non-interactive and hidden from
/// VoiceOver to avoid competing for focus.
struct TopBar: View {
    var body: some View {
        HStack {
            Text("◆ VAULT")
                .font(.system(size: 30, weight: .heavy))
                .kerning(6)
                .foregroundStyle(Theme.accent)
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
