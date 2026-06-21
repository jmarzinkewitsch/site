import SwiftUI

/// Full-bleed backdrop that sits *behind the entire Home screen* — behind the
/// stage info, the shelves and (through the native bar material) the menu bar.
/// Crossfades to the focused item's backdrop and darkens as the user scrolls so
/// the shelves stay readable. Falls back to the plain background when no image.
struct BackdropView: View {
    @Environment(AppEnvironment.self) private var env
    let item: BaseItemDto?
    var imageURL: URL?
    @State private var ambientColor: Color?

    var body: some View {
        ZStack {
            // Backdrop image, full screen. Sized + clipped via GeometryReader so
            // `scaledToFill` can't push the surrounding layout.
            GeometryReader { geo in
                if let item {
                    RemoteImage(url: imageURL ?? env.backdropURL(for: item))
                        .frame(width: geo.size.width, height: geo.size.height)
                        .clipped()
                        .id(item.id)
                        .transition(.opacity)
                        .accessibilityHidden(true)
                } else {
                    Theme.bg
                }
            }

            // Ambient glow tinted by the backdrop dominant color.
            if let ambientColor {
                RadialGradient(
                    gradient: Gradient(colors: [ambientColor.opacity(0.34), .clear]),
                    center: .init(x: 0.78, y: 0.28),
                    startRadius: 0,
                    endRadius: 720
                )
                .blendMode(.screen)
            }

            // Vertical scrim: slight dim under the menu bar, clear through the
            // stage, solid background over the lower shelf band for readability.
            LinearGradient(
                stops: [
                    .init(color: Theme.bg.opacity(0.55), location: 0.0),
                    .init(color: .clear, location: 0.20),
                    .init(color: .clear, location: 0.45),
                    .init(color: Theme.bg.opacity(0.92), location: 0.62),
                    .init(color: Theme.bg, location: 0.78),
                ],
                startPoint: .top, endPoint: .bottom
            )

            // Horizontal scrim from the leading edge so the stage text stays legible.
            LinearGradient(
                colors: [Theme.bg.opacity(Theme.Opacity.scrimStrong), Theme.bg.opacity(Theme.Opacity.scrimMid), .clear],
                startPoint: .leading, endPoint: UnitPoint(x: 0.7, y: 0.5)
            )
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .clipped()
        .ignoresSafeArea()
        .animation(Theme.Anim.crossfade, value: item?.id)
        .task(id: item.flatMap { env.reachableMediaURLIfPresent(imageURL ?? env.backdropURL(for: $0)) }) {
            guard let url = item.flatMap({ env.reachableMediaURLIfPresent(imageURL ?? env.backdropURL(for: $0)) }) else {
                withAnimation(Theme.Anim.crossfade) { ambientColor = nil }
                return
            }
            let color = await AmbientColorProvider.shared.color(for: url)
            withAnimation(Theme.Anim.crossfade) {
                ambientColor = color
            }
        }
    }
}

/// The stage info column at the top of Home: kicker, logo/title, metadata,
/// overview and resume progress of the currently focused item. Drawn on top of
/// `BackdropView`; Home fades it out as the user scrolls so it never overlaps
/// the shelves.
struct StageView: View {
    @Environment(AppEnvironment.self) private var env
    let item: BaseItemDto?

    var body: some View {
        Group {
            if let item {
                info(for: item)
            } else {
                Color.clear
            }
        }
        .padding(.leading, Theme.screenPadding)
        .padding(.top, 150)
        .frame(maxWidth: .infinity, maxHeight: Theme.stageHeight, alignment: .topLeading)
    }

    @ViewBuilder
    private func info(for item: BaseItemDto) -> some View {
        VStack(alignment: .leading, spacing: 16) {
            Text(kicker(for: item))
                .font(.system(size: 21, weight: .bold))
                .kerning(4)
                .foregroundStyle(Theme.accent)

            if let logoURL = env.logoURL(for: item) {
                AsyncImage(url: logoURL) { phase in
                    switch phase {
                    case .success(let image):
                        image
                            .resizable()
                            .scaledToFit()
                            .frame(maxWidth: 640, maxHeight: 132, alignment: .leading)
                            .transition(.opacity)
                    default:
                        Text(item.name ?? "")
                            .font(.system(size: 68, weight: .heavy))
                            .lineLimit(2)
                            .foregroundStyle(Theme.textPrimary)
                    }
                }
                .accessibilityLabel(item.name ?? "")
                .frame(maxWidth: 640, maxHeight: 132, alignment: .leading)
            } else {
                Text(item.name ?? "")
                    .font(.system(size: 68, weight: .heavy))
                    .lineLimit(2)
                    .foregroundStyle(Theme.textPrimary)
            }

            if item.kind == .episode, let seriesName = item.seriesName {
                Text(seriesName)
                    .font(.system(size: 26, weight: .semibold))
                    .foregroundStyle(Theme.textDim)
                    .lineLimit(1)
            }

            HStack(spacing: 18) {
                if let year = item.productionYear { metaText(String(year)) }
                if let duration = item.durationSeconds { metaText(Format.runtime(seconds: duration)) }
                if let rating = item.communityRating { metaText("★ \(String(format: "%.1f", rating))") }
                BadgeRow(badges: Format.badges(for: item.allMediaStreams))
            }

            if let overview = item.overview, !overview.isEmpty {
                Text(overview)
                    .font(.system(size: 24))
                    .foregroundStyle(Theme.textDim)
                    .lineLimit(2)
                    .frame(maxWidth: 880, alignment: .leading)
            }

            if item.resumePositionSeconds > 1, let duration = item.durationSeconds, duration > 0 {
                VStack(alignment: .leading, spacing: 10) {
                    Capsule()
                        .fill(Color.white.opacity(Theme.Opacity.track))
                        .frame(width: Theme.progressBarWidth, height: Theme.progressBarHeight)
                        .overlay(alignment: .leading) {
                            Capsule()
                                .fill(Theme.accent)
                                .frame(width: Theme.progressBarWidth * item.resumePositionSeconds / duration)
                        }
                    Text("Noch \(Format.runtime(seconds: duration - item.resumePositionSeconds)) · ▶ Play-Taste: fortsetzen · Klick: Details")
                        .font(.system(size: 19))
                        .foregroundStyle(Theme.textDim)
                }
                .padding(.top, 8)
            }
        }
    }

    private func kicker(for item: BaseItemDto) -> String {
        switch item.kind {
        case .episode:
            let code = item.episodeCode.map { " · \($0)" } ?? ""
            return "WEITERSCHAUEN\(code)"
        case .series:
            return "SERIE"
        case .movie:
            return item.resumePositionSeconds > 1 ? "WEITERSCHAUEN" : "FILM"
        default:
            return ""
        }
    }

    private func metaText(_ text: String) -> some View {
        Text(text)
            .font(.system(size: 23))
            .foregroundStyle(Theme.textDim)
    }
}
