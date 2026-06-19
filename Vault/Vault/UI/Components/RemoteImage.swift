import SwiftUI

/// AsyncImage wrapper with dark placeholder and fade-in.
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
            default:
                Theme.surface
            }
        }
    }
}
