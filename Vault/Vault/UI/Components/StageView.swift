import SwiftUI

/// The big preview "stage" at the top of Home: shows backdrop, title,
/// metadata and progress of the currently focused item and crossfades
/// when focus moves. Falls back to the poster when no backdrop exists.
struct StageView: View {
    @Environment(AppEnvironment.self) private var env
    let item: BaseItemDto?

    var body: some View {
        ZStack(alignment: .topLeading) {
            // Backdrop, crossfading on item change
            GeometryReader { geo in
                if let item {
                    RemoteImage(url: env.backdropURL(for: item))
                        .frame(width: geo.size.width, height: geo.size.height)
                        .clipped()
                        .id(item.id)
                        .transition(.opacity)
                } else {
                    Theme.bg
                }
            }
            .animation(.easeInOut(duration: 0.4), value: item?.id)

            // Scrims: bottom fade into bg + left fade for text legibility
            LinearGradient(colors: [.clear, Theme.bg], startPoint: .center, endPoint: .bottom)
            LinearGradient(
                colors: [Theme.bg.opacity(0.92), Theme.bg.opacity(0.45), .clear],
                startPoint: .leading, endPoint: UnitPoint(x: 0.7, y: 0.5)
            )

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

            Text(item.kind == .episode ? (item.seriesName ?? item.name ?? "") : (item.name ?? ""))
                .font(.system(size: 68, weight: .heavy))
                .lineLimit(2)
                .foregroundStyle(Theme.textPrimary)

            HStack(spacing: 18) {
                if let year = item.productionYear { metaText(String(year)) }
                if let duration = item.durationSeconds { metaText(Format.runtime(seconds: duration)) }
                if let rating = item.communityRating { metaText("★ \(String(format: "%.1f", rating))") }
                ForEach(Format.badges(for: item.allMediaStreams), id: \.self) { badge in
                    Text(badge)
                        .font(.system(size: 17, weight: .bold))
                        .foregroundStyle(Theme.textDim)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 4)
                        .overlay(RoundedRectangle(cornerRadius: 7).stroke(Theme.textDim.opacity(0.5), lineWidth: 1))
                }
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
                        .fill(Color.white.opacity(0.18))
                        .frame(width: 480, height: 8)
                        .overlay(alignment: .leading) {
                            Capsule()
                                .fill(Theme.accent)
                                .frame(width: 480 * item.resumePositionSeconds / duration)
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
