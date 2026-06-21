import SwiftUI

/// Minimal player chrome: title + codec chips on top, audio/subtitle icon
/// controls and the progress bar with timestamps at the bottom. Auto-hidden
/// by the view model.
/// While scrubbing: shows a virtual playhead knob, a trickplay thumbnail
/// card, and the target time prominently.
struct PlayerOverlayView: View {
    let model: PlayerViewModel
    @FocusState private var focusedControl: TrackControl?

    var body: some View {
        VStack {
            header
            Spacer()
            footer
        }
        .onAppear { updateFocusedControl() }
        .onChange(of: model.controlMode) { _, _ in updateFocusedControl() }
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
                Text(model.durationSeconds > 0
                     ? "-" + Format.clock(seconds: model.durationSeconds - model.currentSeconds)
                     : "--:--")
            }
            .font(.system(size: 24, weight: .medium))
            .monospacedDigit()
            .foregroundStyle(Theme.textPrimary)

            VStack(alignment: .trailing, spacing: 12) {
                trackPanel
                controlRow
            }
            .frame(maxWidth: .infinity, alignment: .trailing)
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

    // MARK: - Track controls

    @ViewBuilder
    private var controlRow: some View {
        if model.hasTrackControls {
            HStack(spacing: 18) {
                Spacer()
                if model.showsAudioControl {
                    trackControl(.audio)
                }
                if model.showsSubtitleControl {
                    trackControl(.subtitles)
                }
            }
        }
    }

    @ViewBuilder
    private func trackControl(_ control: TrackControl) -> some View {
        if model.controlMode == .options {
            Button {
                model.showTrackPanel(control.panel)
            } label: {
                trackControlIcon(control, isFocused: focusedControl == control)
            }
            .buttonStyle(.plain)
            // tvOS otherwise paints its own white focus platter on top of our
            // amber styling; we draw the focus state ourselves.
            .focusEffectDisabled()
            .focused($focusedControl, equals: control)
            .accessibilityLabel(control.accessibilityLabel)
        } else {
            trackControlIcon(control, isFocused: false)
                .accessibilityLabel(control.accessibilityLabel)
        }
    }

    private func trackControlIcon(_ control: TrackControl, isFocused: Bool) -> some View {
        let isActiveSubtitle = control == .subtitles && model.selectedSubtitleTrackIndex != nil
        return Image(systemName: isActiveSubtitle ? control.activeSystemImage : control.systemImage)
            .font(.system(size: 23, weight: .regular))
            .foregroundStyle(isFocused ? Theme.accentText : Theme.accent.opacity(isActiveSubtitle ? 0.95 : 0.7))
            .frame(width: 56, height: 46)
            .background(
                RoundedRectangle(cornerRadius: 8, style: .continuous)
                    .fill(isFocused ? Theme.accent : Color.clear)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 8, style: .continuous)
                    .stroke(Theme.accent.opacity(isFocused ? 1 : 0.55), lineWidth: 1)
            )
            .contentShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
    }

    @ViewBuilder
    private var trackPanel: some View {
        if model.controlMode == .options, let panel = model.openTrackPanel {
            switch panel {
            case .audio:
                trackListPanel {
                    ForEach(model.item.audioTracks, id: \.index) { track in
                        trackRow(title: track.label, isActive: model.selectedAudioTrackIndex == track.index) {
                            model.selectAudioTrack(track)
                            model.closeTrackPanel()
                        }
                    }
                }
            case .subtitles:
                trackListPanel {
                    trackRow(title: "Aus", isActive: model.selectedSubtitleTrackIndex == nil) {
                        model.selectSubtitleTrack(nil)
                        model.closeTrackPanel()
                    }
                    ForEach(model.subtitleTracks, id: \.index) { track in
                        trackRow(title: track.label, isActive: model.selectedSubtitleTrackIndex == track.index) {
                            model.selectSubtitleTrack(track)
                            model.closeTrackPanel()
                        }
                    }
                    Divider()
                        .overlay(Color.white.opacity(0.18))
                        .padding(.vertical, 4)
                    trackRow(title: "Online suchen …", systemImage: "magnifyingglass", isActive: false) {
                        model.presentSubtitleSearch()
                    }
                }
            }
        }
    }

    private func trackListPanel<Content: View>(@ViewBuilder content: () -> Content) -> some View {
        ScrollView {
            VStack(spacing: 6) {
                content()
            }
            .padding(10)
        }
        .frame(width: 560)
        .frame(maxHeight: 430)
        .background(.black.opacity(0.72), in: RoundedRectangle(cornerRadius: 8, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 8, style: .continuous)
                .stroke(Theme.accent.opacity(0.35), lineWidth: 1)
        )
    }

    private func trackRow(
        title: String,
        systemImage: String? = nil,
        isActive: Bool,
        action: @escaping () -> Void
    ) -> some View {
        Button(action: action) {
            HStack(spacing: 14) {
                if let systemImage {
                    Image(systemName: systemImage)
                        .frame(width: 28)
                } else if isActive {
                    Image(systemName: "checkmark")
                        .frame(width: 28)
                } else {
                    Color.clear.frame(width: 28, height: 1)
                }

                Text(title)
                    .font(.system(size: 23, weight: .semibold))
                    .lineLimit(1)
                    .foregroundStyle(isActive ? Theme.accentText : Theme.textPrimary)
                Spacer()
            }
            .padding(.horizontal, 18)
            .padding(.vertical, 13)
            .background(
                RoundedRectangle(cornerRadius: 7, style: .continuous)
                    .fill(isActive ? Theme.accent : Color.white.opacity(0.07))
            )
        }
        .buttonStyle(.plain)
    }

    private func updateFocusedControl() {
        guard model.controlMode == .options else {
            focusedControl = nil
            return
        }
        if model.showsAudioControl {
            focusedControl = .audio
        } else if model.showsSubtitleControl {
            focusedControl = .subtitles
        }
    }
}

private enum TrackControl: Hashable {
    case audio
    case subtitles

    var panel: PlayerViewModel.TrackPanel {
        switch self {
        case .audio: return .audio
        case .subtitles: return .subtitles
        }
    }

    var systemImage: String {
        switch self {
        case .audio: return "speaker.wave.2"
        case .subtitles: return "captions.bubble"
        }
    }

    var activeSystemImage: String {
        switch self {
        case .audio: return systemImage
        case .subtitles: return "captions.bubble.fill"
        }
    }

    var accessibilityLabel: String {
        switch self {
        case .audio: return "Audiospur"
        case .subtitles: return "Untertitel"
        }
    }
}
