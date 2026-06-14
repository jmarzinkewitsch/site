import SwiftUI

/// Shared inline state view for loading / empty / error, so every screen
/// surfaces these the same way instead of ad-hoc labels with drifting styling.
struct StatusView: View {
    enum Kind {
        case loading(String)
        case empty(String)
        case error(String)
    }

    let kind: Kind

    var body: some View {
        switch kind {
        case .loading(let text):
            HStack(spacing: Theme.Spacing.s) {
                ProgressView().tint(Theme.accent)
                Text(text).foregroundStyle(Theme.textDim)
            }
            .accessibilityElement(children: .combine)
        case .empty(let text):
            Label(text, systemImage: "tray")
                .foregroundStyle(Theme.textDim)
        case .error(let text):
            Label(text, systemImage: "exclamationmark.triangle.fill")
                .foregroundStyle(.red)
        }
    }
}
