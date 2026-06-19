import SwiftUI

/// Minimal player chrome: title + codec chips on top, progress bar with
/// timestamps at the bottom. Auto-hidden by the view model.
/// While scrubbing: shows a virtual playhead knob, a trickplay thumbnail
/// card, and the target time prominently.
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
                if model.item.audioTracks.count > 1 {
                    Menu {
                        ForEach(model.item.audioTracks, id: \.index) { track in
                            Button {
                                model.selectAudioTrack(track)
                            } label: {
                                Label(track.label, systemImage: model.selectedAudioTrackIndex == track.index ? "checkmark" : "speaker.wave.2")
                            }
                        }
                    } label: {
                        Label("Audio", systemImage: "speaker.wave.2.fill")
                            .font(.system(size: 17, weight: .bold))
                            .foregroundStyle(Theme.textPrimary)
                            .padding(.horizontal, 12)
                            .padding(.vertical, 5)
                            .background(.black.opacity(0.45), in: RoundedRectangle(cornerRadius: 7))
                    }
                }
                if !model.item.subtitleTracks.isEmpty {
                    Menu {
                        Button {
                            model.selectSubtitleTrack(nil)
                        } label: {
                            Label("Aus", systemImage: model.selectedSubtitleTrackIndex == nil ? "checkmark" : "captions.bubble")
                        }
                        ForEach(model.item.subtitleTracks, id: \.index) { track in
                            Button {
                                model.selectSubtitleTrack(track)
                            } label: {
                                Label(track.label, systemImage: model.selectedSubtitleTrackIndex == track.index ? "checkmark" : "captions.bubble")
                            }
                        }
                    } label: {
                        Label("Untertitel", systemImage: "captions.bubble.fill")
                            .font(.system(size: 17, weight: .bold))
                            .foregroundStyle(Theme.textPrimary)
                            .padding(.horizontal, 12)
                            .padding(.vertical, 5)
                            .background(.black.opacity(0.45), in: RoundedRectangle(cornerRadius: 7))
                    }
                }
                if model.audioWarning != nil {
                    Label("Ohne Ton", systemImage: "speaker.slash.fill")
                        .font(.system(size: 17, weight: .bold))
                        .foregroundStyle(Theme.accent)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 5)
                        .background(.black.opacity(0.45), in: RoundedRectangle(cornerRadius: 7))
                }
                ForEach(model.item.badges, id: \.self) { badge in
                    Text(badge)
                        .font(.system(size: 17, weight: .bold))
                        .foregroundStyle(Theme.textDim)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 5)
                        .background(.black.opacity(0.45), in: RoundedRectangle(cornerRadius: 7))
                }
                if model.state == .paused, !model.isScrubbing {
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
            if model.isScrubbing {
                scrubFooter
            } else {
                normalFooter
            }
        }
        .padding(.horizontal, Theme.screenPadding)
        .padding(.bottom, 70)
        .padding(.top, 90)
        .background(
            LinearGradient(colors: [.clear, .black.opacity(0.75)], startPoint: .top, endPoint: .bottom)
        )
    }

    // MARK: - Normal footer

    private var normalFooter: some View {
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
            .accessibilityElement(children: .ignore)
            .accessibilityLabel("Wiedergabefortschritt")
            .accessibilityValue("\(Int(model.progress * 100)) Prozent")

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
    }

    // MARK: - Scrub footer

    private var scrubFooter: some View {
        let scrubFraction: Double = model.durationSeconds > 0
            ? min(1, max(0, model.scrubTargetSeconds / model.durationSeconds))
            : 0

        return VStack(spacing: 12) {
            // Thumbnail preview card + progress bar in a GeometryReader so we
            // can position the card over the playhead.
            GeometryReader { geo in
                let barWidth = geo.size.width
                let knobX = barWidth * scrubFraction

                // Thumbnail card
                let cardW: CGFloat = 240
                let cardH: CGFloat = 135
                let cardX = min(max(knobX - cardW / 2, 0), barWidth - cardW)

                Group {
                    if let cgImage = model.scrubPreviewImage {
                        Image(uiImage: UIImage(cgImage: cgImage))
                            .resizable()
                            .aspectRatio(contentMode: .fill)
                            .frame(width: cardW, height: cardH)
                            .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
                            .overlay(
                                RoundedRectangle(cornerRadius: 10, style: .continuous)
                                    .stroke(Theme.accent, lineWidth: 2)
                            )
                    } else {
                        // Placeholder when no trickplay data or still loading
                        RoundedRectangle(cornerRadius: 10, style: .continuous)
                            .fill(Color.white.opacity(0.08))
                            .frame(width: cardW, height: cardH)
                            .overlay(
                                RoundedRectangle(cornerRadius: 10, style: .continuous)
                                    .stroke(Color.white.opacity(0.25), lineWidth: 1.5)
                            )
                            .overlay(
                                Image(systemName: "film")
                                    .font(.system(size: 28))
                                    .foregroundStyle(Color.white.opacity(0.4))
                            )
                    }
                }
                .offset(x: cardX, y: -(cardH + 14))

                // Progress bar with knob
                ZStack(alignment: .leading) {
                    Capsule().fill(Color.white.opacity(0.22))
                    Capsule()
                        .fill(Color.white.opacity(0.45))
                        .frame(width: max(8, knobX))
                    // Accent knob at the virtual playhead
                    Circle()
                        .fill(Theme.accent)
                        .frame(width: 22, height: 22)
                        .offset(x: knobX - 11)
                }
                .frame(height: 10)
            }
            .frame(height: 10)
            .padding(.top, 150) // leave room for the thumbnail above the bar

            // Scrub time label
            HStack {
                Text(Format.clock(seconds: model.currentSeconds))
                    .foregroundStyle(Theme.textDim)
                Spacer()
                Text(Format.clock(seconds: model.scrubTargetSeconds))
                    .font(.system(size: 32, weight: .bold))
                    .foregroundStyle(Theme.accent)
                Spacer()
                Text(model.durationSeconds > 0
                     ? "-" + Format.clock(seconds: model.durationSeconds - model.scrubTargetSeconds)
                     : "--:--")
                    .foregroundStyle(Theme.textDim)
            }
            .font(.system(size: 24, weight: .medium))
            .monospacedDigit()
            .foregroundStyle(Theme.textPrimary)
        }
    }

    private var statusText: String {
        switch model.state {
        case .buffering, .opening: return "Lädt …"
        case .seeking: return "Springe …"
        case .paused: return "Pausiert"
        case .ended: return "Ende"
        default: return "◀▶ ±10 s  Wischen = Scrubben"
        }
    }
}
