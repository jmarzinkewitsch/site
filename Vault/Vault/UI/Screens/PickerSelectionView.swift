import SwiftUI

// MARK: - PickerSelectionView

/// "Was schauen wir?" — entry screen where Janno, Tanno, or both configure the
/// four picker facets (persona, mood/fear, genre, length) before requesting
/// suggestions from vault-api.
struct PickerSelectionView: View {
    @Environment(AppEnvironment.self) private var env

    // MARK: Selection state
    @State private var selectedProfile: PickerProfile = .both
    @State private var moodFear: Double = 5
    @State private var selectedGenres: Set<String> = []
    @State private var selectedLength: PickerLength? = nil

    // MARK: Navigation
    @State private var pendingRequest: PickerRequest?

    var body: some View {
        ScrollView(.vertical, showsIndicators: false) {
            VStack(alignment: .leading, spacing: Theme.Spacing.xl) {
                header

                personaSection
                moodSection
                genreSection
                lengthSection
                actionRow

                Color.clear.frame(height: 60)
            }
            .padding(.top, Theme.chromeContentTopPadding)
            .padding(.horizontal, Theme.screenPadding)
        }
        .scrollClipDisabled()
        .background(Theme.bg)
        .ignoresSafeArea()
        .navigationDestination(item: $pendingRequest) { request in
            PickerResultsView(request: request)
        }
    }

    // MARK: Header

    private var header: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Was schauen wir?")
                .font(.system(size: 44, weight: .bold))
                .foregroundStyle(Theme.textPrimary)
            Text("Wählt eure Vorlieben und wir schlagen etwas vor.")
                .font(.system(size: 22))
                .foregroundStyle(Theme.textDim)
        }
    }

    // MARK: Persona ("Wer schaut?")

    private var personaSection: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.m) {
            sectionLabel("Wer schaut?")
            HStack(spacing: 20) {
                ForEach(PickerProfile.allCases, id: \.self) { profile in
                    PersonaPill(profile: profile, isSelected: selectedProfile == profile) {
                        selectedProfile = profile
                    }
                }
            }
        }
    }

    // MARK: Mood / Fear

    private var moodSection: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.m) {
            sectionLabel("Stimmung")
            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    Text("Entspannt")
                        .font(.system(size: 20))
                        .foregroundStyle(Theme.textDim)
                    Spacer()
                    Text("Nervenkitzel")
                        .font(.system(size: 20))
                        .foregroundStyle(Theme.textDim)
                }
                Slider(value: $moodFear, in: 0...10, step: 1)
                    .tint(Theme.accent)
                    .frame(maxWidth: 800)
                HStack(spacing: 6) {
                    Image(systemName: "moon.fill")
                        .foregroundStyle(Theme.accent)
                    Text("Gruselfaktor \(Int(moodFear))")
                        .font(.system(size: 20, weight: .semibold))
                        .foregroundStyle(Theme.textPrimary)
                }
            }
        }
    }

    // MARK: Genre

    private var genreSection: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.m) {
            sectionLabel("Genre")
            WrappingChipRow(chips: pickerGenreChips, selected: $selectedGenres)
        }
    }

    // MARK: Length

    private var lengthSection: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.m) {
            sectionLabel("Länge")
            HStack(spacing: 16) {
                ForEach(PickerLength.allCases, id: \.self) { len in
                    SingleSelectChip(
                        label: len.label,
                        isSelected: selectedLength == len
                    ) {
                        selectedLength = selectedLength == len ? nil : len
                    }
                }
            }
        }
    }

    // MARK: Actions

    private var actionRow: some View {
        HStack(spacing: 24) {
            Button {
                pendingRequest = buildRequest(surprise: false)
            } label: {
                Label("Vorschläge zeigen", systemImage: "sparkles")
                    .font(.system(size: 26, weight: .bold))
                    .padding(.horizontal, 32)
                    .padding(.vertical, 16)
                    .background(Theme.accent, in: RoundedRectangle(cornerRadius: Theme.cornerRadius))
                    .foregroundStyle(Theme.accentText)
            }
            .buttonStyle(CardButtonStyle(scale: 1.06))

            Button {
                pendingRequest = buildRequest(surprise: true)
            } label: {
                Label("Überrasch uns", systemImage: "shuffle")
                    .font(.system(size: 26, weight: .semibold))
                    .padding(.horizontal, 32)
                    .padding(.vertical, 16)
                    .overlay(
                        RoundedRectangle(cornerRadius: Theme.cornerRadius)
                            .stroke(Theme.accent, lineWidth: 2)
                    )
                    .foregroundStyle(Theme.accent)
            }
            .buttonStyle(CardButtonStyle(scale: 1.06))
        }
    }

    // MARK: Helpers

    private func sectionLabel(_ text: String) -> some View {
        Text(text)
            .font(.system(size: 28, weight: .bold))
            .foregroundStyle(Theme.textPrimary)
    }

    private func buildRequest(surprise: Bool) -> PickerRequest {
        PickerRequest(
            profile: selectedProfile.rawValue,
            genres: surprise ? [] : selectedGenres.sorted(),
            moodFear: surprise ? nil : Int(moodFear),
            length: surprise ? nil : selectedLength?.rawValue,
            surprise: surprise,
            excludeIds: []
        )
    }
}

// MARK: - PickerProfile

enum PickerProfile: String, CaseIterable, Hashable {
    case janno = "janno"
    case tanno = "tanno"
    case both  = "both"

    var displayName: String {
        switch self {
        case .janno: return "Janno"
        case .tanno: return "Tanno"
        case .both:  return "Beide"
        }
    }

    /// Single-letter initial shown in the avatar circle, or nil for "Beide".
    var initial: String? {
        switch self {
        case .janno: return "J"
        case .tanno: return "T"
        case .both:  return nil
        }
    }

    /// Avatar accent colour.
    var color: Color {
        switch self {
        case .janno: return Color(red: 232/255, green: 160/255, blue: 48/255)  // amber
        case .tanno: return Color(red: 140/255, green: 100/255, blue: 220/255) // purple
        case .both:  return Theme.textDim
        }
    }
}

// MARK: - PersonaPill

private struct PersonaPill: View {
    let profile: PickerProfile
    let isSelected: Bool
    let action: () -> Void

    @Environment(\.isFocused) private var isFocused

    var body: some View {
        Button(action: action) {
            HStack(spacing: 14) {
                if let initial = profile.initial {
                    Circle()
                        .fill(profile.color)
                        .frame(width: 48, height: 48)
                        .overlay(
                            Text(initial)
                                .font(.system(size: 22, weight: .bold))
                                .foregroundStyle(Theme.accentText)
                        )
                }
                Text(profile.displayName)
                    .font(.system(size: 24, weight: .semibold))
                    .foregroundStyle(isSelected ? Theme.accentText : Theme.textPrimary)
            }
            .padding(.horizontal, 24)
            .padding(.vertical, 14)
            .background(
                isSelected ? Theme.accent : Theme.surface,
                in: RoundedRectangle(cornerRadius: Theme.cornerRadius)
            )
            .overlay(
                RoundedRectangle(cornerRadius: Theme.cornerRadius)
                    .stroke(
                        isSelected ? Theme.accent : (isFocused ? Theme.accent : Color.clear),
                        lineWidth: 2
                    )
            )
            .animation(Theme.Anim.focusRing, value: isFocused)
        }
        .buttonStyle(CardButtonStyle(scale: 1.06))
    }
}

// MARK: - WrappingChipRow (genre multi-select)

private struct WrappingChipRow: View {
    let chips: [String]
    @Binding var selected: Set<String>
    @FocusState private var focusedChip: String?

    var body: some View {
        // tvOS doesn't have a native wrapping layout pre-iOS 16, so we use
        // a fixed-column LazyVGrid which keeps the chips reachable by D-pad.
        let columns = Array(repeating: GridItem(.flexible(), spacing: 20), count: 4)
        LazyVGrid(columns: columns, alignment: .leading, spacing: 16) {
            ForEach(chips, id: \.self) { chip in
                let isSelected = selected.contains(chip.lowercased())
                Button {
                    let key = chip.lowercased()
                    if selected.contains(key) {
                        selected.remove(key)
                    } else {
                        selected.insert(key)
                    }
                } label: {
                    Text(chip)
                        .font(.system(size: 22, weight: .semibold))
                        .foregroundStyle(isSelected ? Theme.accentText : Theme.textPrimary)
                        .padding(.horizontal, 22)
                        .padding(.vertical, 12)
                        .frame(maxWidth: .infinity)
                        .background(
                            isSelected ? Theme.accent : Theme.surface,
                            in: RoundedRectangle(cornerRadius: Theme.cornerRadius)
                        )
                        .overlay(
                            RoundedRectangle(cornerRadius: Theme.cornerRadius)
                                .stroke(
                                    isSelected ? Theme.accent : Theme.textDim.opacity(0.25),
                                    lineWidth: isSelected ? 0 : 1
                                )
                        )
                }
                .buttonStyle(CardButtonStyle(scale: 1.06))
                .focused($focusedChip, equals: chip)
            }
        }
        .frame(maxWidth: 900)
    }
}

// MARK: - SingleSelectChip

private struct SingleSelectChip: View {
    let label: String
    let isSelected: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Text(label)
                .font(.system(size: 22, weight: .semibold))
                .foregroundStyle(isSelected ? Theme.accentText : Theme.textPrimary)
                .padding(.horizontal, 28)
                .padding(.vertical, 14)
                .background(
                    isSelected ? Theme.accent : Theme.surface,
                    in: RoundedRectangle(cornerRadius: Theme.cornerRadius)
                )
                .overlay(
                    RoundedRectangle(cornerRadius: Theme.cornerRadius)
                        .stroke(
                            isSelected ? Theme.accent : Theme.textDim.opacity(0.25),
                            lineWidth: isSelected ? 0 : 1
                        )
                )
        }
        .buttonStyle(CardButtonStyle(scale: 1.06))
    }
}
