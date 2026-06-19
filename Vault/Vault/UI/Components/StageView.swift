import SwiftUI

/// The big preview "stage" at the top of Home: shows backdrop, title,
/// metadata and progress of the currently focused item and crossfades
/// when focus moves. Falls back to the poster when no backdrop exists.
struct StageView: View {
    @Environment(AppEnvironment.self) private var env
    let item: BaseItemDto?
    var imageURL: URL?

    var body: some View {
        ZStack(alignment: .topLeading) {
            // Backdrop + scrims are full-bleed; the info column stays inside the
            // safe area so it stays aligned with the shelf headers below.
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
            .animation(Theme.Anim.crossfade, value: item?.id)
            .ignoresSafeArea()

            LinearGradient(colors: [.clear, Theme.bg], startPoint: .center, endPoint: .bottom)
                .ignoresSafeArea()
            LinearGradient(
                colors: [Theme.bg.opacity(Theme.Opacity.scrimStrong), Theme.bg.opacity(Theme.Opacity.scrimMid), .clear],
                startPoint: .leading, endPoint: UnitPoint(x: 0.7, y: 0.5)
            )
            .ignoresSafeArea()

            if let item {
                info(for: item)
                    .padding(.leading, Theme.screenPadding)
                    .padding(.top, 150)
            }
        }
        .frame(height: Theme.stageHeight)
        .ignoresSafeArea(edges: .top)
    }

    @ViewBuilder
    private func info(for item: BaseItemDto) -> some View {
        VStack(alignment: .leading, spacing: 16) {
            Text(kicker(for: item))
                .font(.system(size: 21, weight: .bold))
                .kerning(4)
                .foregroundStyle(Theme.accent)

            Text(item.name ?? "")
                .font(.system(size: 68, weight: .heavy))
                .lineLimit(2)
                .foregroundStyle(Theme.textPrimary)

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
