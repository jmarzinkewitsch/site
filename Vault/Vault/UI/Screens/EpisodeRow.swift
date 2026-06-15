import SwiftUI

/// One episode in the season list: 16:9 thumb, number, title, runtime,
/// watched check / progress.
struct EpisodeRow: View {
    @Environment(AppEnvironment.self) private var env
    let episode: BaseItemDto
    let watchedOverride: Bool?
    let toggleWatched: (() -> Void)?
    let action: () -> Void

    init(
        episode: BaseItemDto,
        watchedOverride: Bool? = nil,
        toggleWatched: (() -> Void)? = nil,
        action: @escaping () -> Void
    ) {
        self.episode = episode
        self.watchedOverride = watchedOverride
        self.toggleWatched = toggleWatched
        self.action = action
    }

    var body: some View {
        Button(action: action) {
            HStack(alignment: .top, spacing: 28) {
                ZStack(alignment: .bottomLeading) {
                    RemoteImage(url: env.backdropURL(for: episode))
                        .frame(width: Theme.episodeThumbWidth, height: Theme.episodeThumbHeight)
                    if displayedWatchedFraction > 0 {
                        GeometryReader { geo in
                            Rectangle()
                                .fill(Theme.accent)
                                .frame(width: geo.size.width * displayedWatchedFraction, height: 5)
                                .frame(maxHeight: .infinity, alignment: .bottom)
                        }
                    }
                }
                .frame(width: Theme.episodeThumbWidth, height: Theme.episodeThumbHeight)
                .clipShape(RoundedRectangle(cornerRadius: 10))
                .modifier(FocusRing(cornerRadius: 10))
                .accessibilityHidden(true)

                VStack(alignment: .leading, spacing: 8) {
                    HStack(spacing: 14) {
                        if let number = episode.indexNumber {
                            Text("\(number)")
                                .font(.system(size: 24, weight: .bold))
                                .foregroundStyle(Theme.accent)
                        }
                        Text(episode.name ?? "—")
                            .font(.system(size: 26, weight: .semibold))
                            .lineLimit(1)
                            .foregroundStyle(Theme.textPrimary)
                        if displayedIsPlayed {
                            Image(systemName: "checkmark.circle.fill")
                                .font(.system(size: 20))
                                .foregroundStyle(Theme.textDim)
                                .accessibilityHidden(true)
                        }
                    }
                    if let duration = episode.durationSeconds {
                        Text(Format.runtime(seconds: duration))
                            .font(.system(size: 20))
                            .foregroundStyle(Theme.textDim)
                    }
                    if let overview = episode.overview, !overview.isEmpty {
                        Text(overview)
                            .font(.system(size: 20))
                            .foregroundStyle(Theme.textDim)
                            .lineLimit(2)
                    }
                }
                Spacer(minLength: 0)
            }
            .padding(18)
        }
        .buttonStyle(CardButtonStyle(scale: 1.02))
        .contextMenu {
            if let toggleWatched {
                Button(displayedIsPlayed ? "Als ungesehen markieren" : "Als gesehen markieren") {
                    toggleWatched()
                }
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(accessibilityLabel)
    }

    private var displayedIsPlayed: Bool {
        watchedOverride ?? episode.isPlayed
    }

    private var displayedWatchedFraction: Double {
        displayedIsPlayed ? 1.0 : episode.watchedFraction
    }

    private var accessibilityLabel: String {
        var parts: [String] = []
        if let number = episode.indexNumber { parts.append("Folge \(number)") }
        parts.append(episode.name ?? "Unbenannt")
        if let duration = episode.durationSeconds { parts.append(Format.runtime(seconds: duration)) }
        if displayedIsPlayed { parts.append("gesehen") }
        return parts.joined(separator: ", ")
    }
}
