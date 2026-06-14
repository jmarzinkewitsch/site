import SwiftUI

/// Post-play prompt for Vault-owned profile snapshots.
struct PostPlayRatingView: View {
    let item: PlayerItem
    let isSaving: Bool
    let errorMessage: String?
    let onSave: (VaultRatingSnapshot) -> Void
    let onSkip: () -> Void

    @State private var jannoRating = 0
    @State private var tannoRating = 0
    @State private var fearFactor = 0.0

    var body: some View {
        VStack(alignment: .leading, spacing: 28) {
            VStack(alignment: .leading, spacing: 8) {
                Text("Wie war’s?")
                    .font(.system(size: 44, weight: .heavy))
                    .foregroundStyle(Theme.textPrimary)
                Text(item.title)
                    .font(.system(size: 24, weight: .semibold))
                    .foregroundStyle(Theme.textDim)
            }

            ratingRow(title: "Janno", value: $jannoRating)
            ratingRow(title: "Tanno", value: $tannoRating)

            VStack(alignment: .leading, spacing: 10) {
                HStack {
                    Label("Tannos Gruselfaktor", systemImage: "moon.stars.fill")
                    Spacer()
                    Text("\(Int(fearFactor))/20")
                }
                .font(.system(size: 22, weight: .bold))
                .foregroundStyle(Theme.textPrimary)

                Slider(value: $fearFactor, in: 0...20, step: 1)
                    .tint(Theme.accent)
                    .frame(width: 620)
            }

            if let errorMessage {
                Text(errorMessage)
                    .font(.system(size: 18, weight: .semibold))
                    .foregroundStyle(.red)
            }

            HStack(spacing: 20) {
                Button {
                    onSave(snapshot)
                } label: {
                    if isSaving {
                        Label("Speichert …", systemImage: "hourglass")
                    } else {
                        Label("Bewertungen speichern", systemImage: "checkmark.circle.fill")
                    }
                }
                .disabled(isSaving || (jannoRating == 0 && tannoRating == 0 && fearFactor == 0))

                Button("Später") { onSkip() }
                    .disabled(isSaving)
            }
        }
        .padding(46)
        .frame(width: 780, alignment: .leading)
        .background(Theme.bg.opacity(0.92), in: RoundedRectangle(cornerRadius: 34, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 34, style: .continuous)
                .stroke(Theme.textDim.opacity(0.25), lineWidth: 1)
        )
        .shadow(radius: 30)
    }

    private var snapshot: VaultRatingSnapshot {
        VaultRatingSnapshot(
            title: item.title,
            type: item.type,
            year: item.year,
            tmdbId: item.tmdbId,
            imdbId: item.imdbId,
            jannoRating: jannoRating > 0 ? Double(jannoRating * 2) : nil,
            tannoRating: tannoRating > 0 ? Double(tannoRating * 2) : nil,
            tannoFearFactor: fearFactor
        )
    }

    private func ratingRow(title: String, value: Binding<Int>) -> some View {
        HStack(spacing: 18) {
            Text(title)
                .font(.system(size: 24, weight: .bold))
                .foregroundStyle(Theme.textPrimary)
                .frame(width: 170, alignment: .leading)
            HStack(spacing: 8) {
                ForEach(1...5, id: \.self) { star in
                    Button {
                        value.wrappedValue = star
                    } label: {
                        Image(systemName: star <= value.wrappedValue ? "star.fill" : "star")
                            .font(.system(size: 32, weight: .bold))
                            .foregroundStyle(star <= value.wrappedValue ? Theme.accent : Theme.textDim)
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel("\(title): \(star) von 5 Sternen")
                }
            }
        }
    }
}
