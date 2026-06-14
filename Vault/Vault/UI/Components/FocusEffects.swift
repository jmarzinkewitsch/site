import SwiftUI

/// Scales the whole card and adds a soft shadow on focus.
/// Must be used inside a focusable container (e.g. a Button label) —
/// reads focus from the environment.
struct FocusScale: ViewModifier {
    @Environment(\.isFocused) private var isFocused
    var scale: CGFloat = 1.12

    func body(content: Content) -> some View {
        content
            .scaleEffect(isFocused ? scale : 1)
            .shadow(
                color: isFocused ? .black.opacity(0.6) : .clear,
                radius: 24, y: 14
            )
            .animation(Theme.Anim.focusScale, value: isFocused)
    }
}

/// Amber focus ring with offset, applied to the artwork only (not the labels).
struct FocusRing: ViewModifier {
    @Environment(\.isFocused) private var isFocused
    var cornerRadius: CGFloat = Theme.cornerRadius

    func body(content: Content) -> some View {
        content
            .overlay(
                RoundedRectangle(cornerRadius: cornerRadius + 5)
                    .stroke(Theme.accent, lineWidth: isFocused ? 5 : 0)
                    .padding(-9)
            )
            .animation(Theme.Anim.focusRing, value: isFocused)
    }
}

/// Button style that disables the system card treatment so our own
/// focus effects (scale + amber ring) are the only ones applied.
struct CardButtonStyle: ButtonStyle {
    var scale: CGFloat = 1.12

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .modifier(FocusScale(scale: scale))
    }
}
