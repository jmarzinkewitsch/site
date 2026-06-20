import SwiftUI

/// AsyncImage wrapper: a subtle shimmer while loading, fade-in on success,
/// flat surface on failure.
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
                ShimmerView()
            case .failure:
                Theme.surface
            @unknown default:
                Theme.surface
            }
        }
    }
}

/// A dim surface with a soft light band sweeping left-to-right — the loading
/// placeholder for remote images, so a slow load reads as "lädt" instead of a
/// dead grey rectangle.
private struct ShimmerView: View {
    @State private var offset: CGFloat = -1

    var body: some View {
        GeometryReader { geo in
            Theme.surface
                .overlay(
                    LinearGradient(
                        gradient: Gradient(colors: [.clear, Color.white.opacity(0.08), .clear]),
                        startPoint: .leading,
                        endPoint: .trailing
                    )
                    .frame(width: geo.size.width * 0.5)
                    .offset(x: offset * geo.size.width)
                )
                .clipped()
        }
        .onAppear {
            withAnimation(.linear(duration: 1.3).repeatForever(autoreverses: false)) {
                offset = 1.5
            }
        }
    }
}
