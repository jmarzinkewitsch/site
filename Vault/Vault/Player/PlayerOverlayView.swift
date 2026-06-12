import SwiftUI

/// Minimal player chrome: title + codec chips on top, progress bar with
/// timestamps at the bottom. Auto-hidden by the view model.
struct PlayerOverlayView: View {
    let model: PlayerViewModel

    var body: some View {
        VStack {
            header
            Spacer()
            footer
        }
    }

    private var header: some View {
        HStack(alignment: .firstTextBaseline, spacing: 24) {
            VStack(alignment: .leading, spacing: 6) {
                Text(model.item.title)
                    .font(.system(size: 38, weight: .bold))
                    .foregroundStyle(Theme.textPrimary)
                if let subtitle = model.item.subtitle {
                    Text(subtitle)
                        .font(.system(size: 24))
                        .foregroundStyle(Theme.textDim)
                }
            }
            Spacer()
            HStack(spacing: 12) {
                ForEach(model.item.badges, id: \.self) { badge in
                    Text(badge)
                        .font(.system(size: 17, weight: .bold))
                        .foregroundStyle(Theme.textDim)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 5)
                        .background(.black.opacity(0.45), in: RoundedRectangle(cornerRadius: 7))
                }
                if model.state == .paused {
                    Image(systemName: "pause.fill")
                        .font(.system(size: 26))
                        .foregroundStyle(Theme.accent)
                }
            }
        }
        .padding(.horizontal, Theme.screenPadding)
        .padding(.top, 60)
        .background(
            LinearGradient(colors: [.black.opacity(0.7), .clear], startPoint: .top, endPoint: .bottom)
        )
    }

    private var footer: some View {
        VStack(spacing: 16) {
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    Capsule().fill(Color.white.opacity(0.22))
                    Capsule()
                        .fill(Theme.accent)
                        .frame(width: max(8, geo.size.width * model.progress))
                }
            }
            .frame(height: 10)

            HStack {
                Text(Format.clock(seconds: model.currentSeconds))
                Spacer()
                Text(statusText)
                    .foregroundStyle(Theme.textDim)
                Spacer()
                Text(model.durationSeconds > 0
                     ? "-" + Format.clock(seconds: model.durationSeconds - model.currentSeconds)
                     : "--:--")
            }
            .font(.system(size: 24, weight: .medium))
            .monospacedDigit()
            .foregroundStyle(Theme.textPrimary)
        }
        .padding(.horizontal, Theme.screenPadding)
        .padding(.bottom, 70)
        .padding(.top, 90)
        .background(
            LinearGradient(colors: [.clear, .black.opacity(0.75)], startPoint: .top, endPoint: .bottom)
        )
    }

    private var statusText: String {
        switch model.state {
        case .buffering, .opening: return "Lädt …"
        case .seeking: return "Springe …"
        case .paused: return "Pausiert"
        case .ended: return "Ende"
        default: return "◀ ▶ ±10 s"
        }
    }
}
