import SwiftUI

// MARK: - PersonaProfileSetupView

/// Minimal screen for editing Janno's and Tanno's taste profiles.
/// Reachable from SettingsView → "Geschmacksprofile".
struct PersonaProfileSetupView: View {
    @Environment(AppEnvironment.self) private var env

    @State private var profiles: [PersonaProfile] = []
    @State private var isLoading = true
    @State private var errorMessage: String?
    @State private var saveMessage: String?
    @State private var selectedPerson = "janno"

    var body: some View {
        ScrollView(.vertical, showsIndicators: false) {
            VStack(alignment: .leading, spacing: Theme.Spacing.xl) {
                header

                if isLoading {
                    ProgressView("Lade Profile …")
                        .foregroundStyle(Theme.textDim)
                } else if let err = errorMessage {
                    StatusView(kind: .error(err))
                } else {
                    personTabs
                    if let idx = profiles.firstIndex(where: { $0.person == selectedPerson }) {
                        profileEditor(index: idx)
                    }
                    if let msg = saveMessage {
                        Text(msg)
                            .font(.system(size: 20))
                            .foregroundStyle(Theme.accent)
                    }
                }

                Color.clear.frame(height: 60)
            }
            .padding(.top, Theme.chromeContentTopPadding)
            .padding(.horizontal, Theme.screenPadding)
        }
        .scrollClipDisabled()
        .background(Theme.bg)
        .ignoresSafeArea()
        .task { await load() }
    }

    // MARK: Header

    private var header: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Geschmacksprofile")
                .font(.system(size: 44, weight: .bold))
                .foregroundStyle(Theme.textPrimary)
            Text("Lieblingsgenres und Komfortzonen für bessere Vorschläge.")
                .font(.system(size: 22))
                .foregroundStyle(Theme.textDim)
        }
    }

    // MARK: Person toggle tabs

    private var personTabs: some View {
        HStack(spacing: 20) {
            ForEach(profiles) { profile in
                let isSelected = profile.person == selectedPerson
                Button(profile.person.capitalized) {
                    selectedPerson = profile.person
                    saveMessage = nil
                }
                .foregroundStyle(isSelected ? Theme.accentText : Theme.textPrimary)
                .padding(.horizontal, 28)
                .padding(.vertical, 14)
                .background(isSelected ? Theme.accent : Theme.surface,
                            in: RoundedRectangle(cornerRadius: Theme.cornerRadius))
                .buttonStyle(CardButtonStyle(scale: 1.06))
            }
        }
    }

    // MARK: Profile editor

    @ViewBuilder
    private func profileEditor(index: Int) -> some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.l) {
            genreEditor(index: index)
            fearEditor(index: index)
            saveButton(index: index)
        }
    }

    private func genreEditor(index: Int) -> some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.m) {
            Text("Lieblingsgenres")
                .font(.system(size: 28, weight: .bold))
                .foregroundStyle(Theme.textPrimary)

            let columns = Array(repeating: GridItem(.flexible(), spacing: 16), count: 4)
            LazyVGrid(columns: columns, alignment: .leading, spacing: 14) {
                ForEach(pickerGenreChips, id: \.self) { chip in
                    let key = chip.lowercased()
                    let isSelected = profiles[index].favoriteGenres.contains(key)
                    Button {
                        if isSelected {
                            profiles[index].favoriteGenres.removeAll { $0 == key }
                        } else {
                            profiles[index].favoriteGenres.append(key)
                        }
                    } label: {
                        Text(chip)
                            .font(.system(size: 20, weight: .semibold))
                            .foregroundStyle(isSelected ? Theme.accentText : Theme.textPrimary)
                            .padding(.horizontal, 18)
                            .padding(.vertical, 10)
                            .frame(maxWidth: .infinity)
                            .background(
                                isSelected ? Theme.accent : Theme.surface,
                                in: RoundedRectangle(cornerRadius: Theme.cornerRadius)
                            )
                            .overlay(
                                RoundedRectangle(cornerRadius: Theme.cornerRadius)
                                    .stroke(
                                        isSelected ? Theme.accent : Theme.textDim.opacity(0.2),
                                        lineWidth: isSelected ? 0 : 1
                                    )
                            )
                    }
                    .buttonStyle(CardButtonStyle(scale: 1.06))
                }
            }
            .frame(maxWidth: 900)
        }
    }

    private func fearEditor(index: Int) -> some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.m) {
            Text("Grusel-Komfortzone")
                .font(.system(size: 28, weight: .bold))
                .foregroundStyle(Theme.textPrimary)

            VStack(alignment: .leading, spacing: 10) {
                HStack {
                    Text("Kein Grusel")
                        .font(.system(size: 20))
                        .foregroundStyle(Theme.textDim)
                    Spacer()
                    Text("Sehr gerne")
                        .font(.system(size: 20))
                        .foregroundStyle(Theme.textDim)
                }
                Slider(
                    value: Binding(
                        get: { Double(profiles[index].fearComfort) },
                        set: { profiles[index].fearComfort = Int($0) }
                    ),
                    in: 0...10,
                    step: 1
                )
                .tint(Theme.accent)
                .frame(maxWidth: 700)
                HStack(spacing: 6) {
                    Image(systemName: "moon.fill")
                        .foregroundStyle(Theme.accent)
                    Text("Stufe \(profiles[index].fearComfort)")
                        .font(.system(size: 20, weight: .semibold))
                        .foregroundStyle(Theme.textPrimary)
                }
            }
        }
    }

    private func saveButton(index: Int) -> some View {
        Button {
            Task { await save(index: index) }
        } label: {
            Label("Speichern", systemImage: "checkmark.circle.fill")
                .font(.system(size: 24, weight: .bold))
                .foregroundStyle(Theme.accentText)
                .padding(.horizontal, 32)
                .padding(.vertical, 14)
                .background(Theme.accent, in: RoundedRectangle(cornerRadius: Theme.cornerRadius))
        }
        .buttonStyle(CardButtonStyle(scale: 1.06))
    }

    // MARK: Data

    @MainActor
    private func load() async {
        guard let discover = env.discover else {
            errorMessage = "Nicht verbunden."
            isLoading = false
            return
        }
        do {
            profiles = try await discover.profiles()
            // Ensure both persons exist as editable stubs.
            for person in ["janno", "tanno"] {
                if !profiles.contains(where: { $0.person == person }) {
                    profiles.append(PersonaProfile(person: person, favoriteGenres: [], fearComfort: 5))
                }
            }
            isLoading = false
        } catch {
            errorMessage = error.localizedDescription
            isLoading = false
        }
    }

    @MainActor
    private func save(index: Int) async {
        guard let discover = env.discover else { return }
        do {
            try await discover.saveProfile(profiles[index])
            saveMessage = "Profil gespeichert."
        } catch {
            saveMessage = "Fehler: \(error.localizedDescription)"
        }
    }
}
