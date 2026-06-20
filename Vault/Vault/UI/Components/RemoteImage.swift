import SwiftUI

/// AsyncImage wrapper: a subtle shimmering placeholder while loading, fade-in
/// on success, flat surface on failure.
struct RemoteImage: View {
    @Environment(AppEnvironment.self) private var env
    let url: URL?

    var body: some View {
        AsyncImage(url: env.reachableMediaURLIfPresent(url), transaction: Transaction(animation: Theme.Anim.imageFade)) { phase in
            switch phase {
            case .success(let image):
                image
                    .resizable()
                    .scaledToFill()
                    .transition(.opacity)
            case .empty:
                Color.white.opacity(0.06).shimmering()
            case .failure:
                Theme.surface
            @unknown default:
                Theme.surface
            }
        }
    }
}

/// A soft light band sweeping across a filled shape — reads as "lädt" instead
/// of a dead grey rectangle. Apply to a colour/shape; the sweep is masked to it.
struct Shimmer: ViewModifier {
    @State private var phase: CGFloat = -1

    func body(content: Content) -> some View {
        content.overlay(
            GeometryReader { geo in
                LinearGradient(
                    gradient: Gradient(colors: [.clear, Color.white.opacity(0.10), .clear]),
                    startPoint: .leading,
                    endPoint: .trailing
                )
                .frame(width: geo.size.width * 0.5)
                .offset(x: phase * geo.size.width)
            }
            .mask(content)
        )
        .onAppear {
            withAnimation(.linear(duration: 1.4).repeatForever(autoreverses: false)) {
                phase = 1.5
            }
        }
    }
}

extension View {
    func shimmering() -> some View { modifier(Shimmer()) }
}
