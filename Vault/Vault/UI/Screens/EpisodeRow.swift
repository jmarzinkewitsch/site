import SwiftUI

/// One episode in the season list: 16:9 thumb, number, title, runtime,
/// watched check / progress.
struct EpisodeRow: View {
    @Environment(AppEnvironment.self) private var env
    let episode: BaseItemDto
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(alignment: .top, spacing: 28) {
                ZStack(alignment: .bottomLeading) {
                    RemoteImage(url: env.backdropURL(for: episode, maxWidth: 500))
                        .frame(width: 260, height: 146)
                    if let pct = episode.userData?.playedPercentage, pct > 0 {
                        GeometryReader { geo in
                            Rectangle()
                                .fill(Theme.accent)
                                .frame(width: geo.size.width * pct / 100, height: 5)
                                .frame(maxHeight: .infinity, alignment: .bottom)
                        }
                    }
                }
                .frame(width: 260, height: 146)
                .clipShape(RoundedRectangle(cornerRadius: 10))
                .modifier(FocusRing(cornerRadius: 10))

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
                        if episode.userData?.played == true {
                            Image(systemName: "checkmark.circle.fill")
                                .font(.system(size: 20))
                                .foregroundStyle(Theme.textDim)
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
    }
}
