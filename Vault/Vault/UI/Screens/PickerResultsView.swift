import SwiftUI

// MARK: - PickerResultsView

/// Displays the picker results: two co-equal hero cards (library + discover)
/// and an alternatives shelf. Supports reshuffling by passing already-seen ids
/// back to the backend.
struct PickerResultsView: View {
    @Environment(AppEnvironment.self) private var env
    @Environment(\.dismiss) private var dismiss

    let request: PickerRequest

    @State private var state: LoadState = .loading
    @State private var playerItem: PlayerItem?
    @FocusState private var focusedAlt: String?

    // Track which ids have been shown so reshuffle excludes them.
    @State private var seenIds: [String] = []

    enum LoadState {
        case loading
        case loaded(PickerResponse)
        case error(String)
    }

    var body: some View {
        ScrollView(.vertical, showsIndicators: false) {
            VStack(alignment: .leading, spacing: Theme.Spacing.xl) {
                recapRow

                switch state {
                case .loading:
                    ProgressView("Suche Vorschläge …")
                        .foregroundStyle(Theme.textDim)
                        .padding(.horizontal, Theme.screenPadding)
                        .padding(.top, 80)

                case .error(let msg):
                    StatusView(kind: .error(msg))
                        .padding(.horizontal, Theme.screenPadding)

                case .loaded(let response):
                    heroRow(response)
                    if !response.alternatives.isEmpty {
                        alternativesShelf(response.alternatives)
                    }
                    reshuffleButton(response)
                }

                Color.clear.frame(height: 60)
            }
            .padding(.top, Theme.chromeContentTopPadding)
        }
        .scrollClipDisabled()
        .background(Theme.bg)
        .ignoresSafeArea()
        .task { await load(request: currentRequest()) }
        .fullScreenCover(item: $playerItem) { item in
            PlayerScreen(item: item, reporter: env.reporter)
        }
    }

    // MARK: Recap Row

    private var recapRow: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 12) {
                recapChip(request.profile == "both" ? "Beide" : request.profile.capitalized,
                          icon: "person.2.fill")
                if let mf = request.moodFear {
                    recapChip("Stimmung \(mf)", icon: "moon.fill")
                }
                ForEach(request.genres, id: \.self) { genre in
                    recapChip(genre.capitalized, icon: nil)
                }
                if let len = request.length {
                    recapChip(PickerLength(rawValue: len)?.label ?? len, icon: "clock")
                }
                if request.surprise {
                    recapChip("Überraschung", icon: "shuffle")
                }

                // "Ändern" pops back to PickerSelectionView
                Button {
                    dismiss()
                } label: {
                    Label("Ändern", systemImage: "slider.horizontal.3")
                        .font(.system(size: 18, weight: .semibold))
                        .foregroundStyle(Theme.accent)
                        .padding(.horizontal, 16)
                        .padding(.vertical, 8)
                        .overlay(
                            Capsule().stroke(Theme.accent, lineWidth: 1.5)
                        )
                }
                .buttonStyle(CardButtonStyle(scale: 1.06))
            }
            .padding(.horizontal, Theme.screenPadding)
        }
    }

    private func recapChip(_ label: String, icon: String?) -> some View {
        Group {
            if let icon {
                Label(label, systemImage: icon)
            } else {
                Text(label)
            }
        }
        .font(.system(size: 18, weight: .semibold))
        .foregroundStyle(Theme.textDim)
        .padding(.horizontal, 16)
        .padding(.vertical, 8)
        .background(Theme.surface, in: Capsule())
    }

    // MARK: Hero Row

    @ViewBuilder
    private func heroRow(_ response: PickerResponse) -> some View {
        HStack(alignment: .top, spacing: 40) {
            if let lib = response.libraryPick {
                HeroCard(pick: lib, kicker: "AUS DEINER BIBLIOTHEK", kickerColor: .green) {
                    Task { await playLibraryItem(lib) }
                }
            }
            if let disc = response.discoverPick {
                HeroCard(pick: disc, kicker: "ZUM ENTDECKEN", kickerColor: Theme.accent) {
                    // Routing handled inside HeroCard via NavigationLink
                }
            }
        }
        .padding(.horizontal, Theme.screenPadding)
    }

    // MARK: Alternatives Shelf

    private func alternativesShelf(_ items: [PickItem]) -> some View {
        MediaShelf(title: "Weitere Vorschläge") {
            ForEach(items) { pick in
                alternativeCard(pick)
            }
        }
    }

    @ViewBuilder
    private func alternativeCard(_ pick: PickItem) -> some View {
        let imageURL = pick.backdropUrl.flatMap { URL(string: $0) }
                    ?? pick.posterUrl.flatMap { URL(string: $0) }
        Group {
            if pick.isPlayable, let libraryId = pick.libraryId {
                Button {
                    Task { await playById(libraryId) }
                } label: {
                    altCardLabel(pick, imageURL: imageURL)
                }
                .onPlayPauseCommand { Task { await playById(libraryId) } }
            } else {
                NavigationLink {
                    RequestDetailView(item: pick.asRecommendationItem)
                } label: {
                    altCardLabel(pick, imageURL: imageURL)
                }
            }
        }
        .buttonStyle(CardButtonStyle())
        .focused($focusedAlt, equals: pick.id)
    }

    private func altCardLabel(_ pick: PickItem, imageURL: URL?) -> some View {
        let width: CGFloat = Theme.posterWidth
        return VStack(alignment: .leading, spacing: 10) {
            ZStack(alignment: .topTrailing) {
                RemoteImage(url: imageURL)
                    .frame(width: width, height: width * Theme.posterAspectRatio)
                    .clipShape(RoundedRectangle(cornerRadius: Theme.cornerRadius))
                    .modifier(FocusRing())
                    .accessibilityHidden(true)

                // Source badge: green play-dot for library, amber "+" for discover
                sourceBadge(pick)
                    .padding(8)
            }

            Text(pick.title)
                .font(.system(size: 22, weight: .semibold))
                .lineLimit(1)
                .foregroundStyle(Theme.textPrimary)
                .frame(width: width, alignment: .leading)

            Text(pick.reason)
                .font(.system(size: 17))
                .lineLimit(2)
                .foregroundStyle(Theme.textDim)
                .frame(width: width, height: 46, alignment: .topLeading)
        }
        .frame(width: width, alignment: .leading)
    }

    @ViewBuilder
    private func sourceBadge(_ pick: PickItem) -> some View {
        if pick.source == "library" {
            Image(systemName: "play.fill")
                .font(.system(size: 13, weight: .bold))
                .foregroundStyle(Theme.accentText)
                .padding(7)
                .background(.green, in: Circle())
        } else {
            Image(systemName: "plus")
                .font(.system(size: 13, weight: .bold))
                .foregroundStyle(Theme.accentText)
                .padding(7)
                .background(Theme.accent, in: Circle())
        }
    }

    // MARK: Reshuffle

    private func reshuffleButton(_ response: PickerResponse) -> some View {
        HStack {
            Button {
                Task { await reshuffle(response) }
            } label: {
                Label("Andere zeigen ↻", systemImage: "arrow.2.circlepath")
                    .font(.system(size: 24, weight: .semibold))
                    .foregroundStyle(Theme.textPrimary)
                    .padding(.horizontal, 36)
                    .padding(.vertical, 16)
                    .overlay(
                        RoundedRectangle(cornerRadius: Theme.cornerRadius)
                            .stroke(Theme.textDim.opacity(0.4), lineWidth: 1.5)
                    )
            }
            .buttonStyle(CardButtonStyle(scale: 1.06))
        }
        .padding(.horizontal, Theme.screenPadding)
    }

    // MARK: Load / Reshuffle logic

    private func currentRequest() -> PickerRequest {
        PickerRequest(
            profile: request.profile,
            genres: request.genres,
            moodFear: request.moodFear,
            length: request.length,
            surprise: request.surprise,
            excludeIds: seenIds
        )
    }

    @MainActor
    private func load(request: PickerRequest) async {
        state = .loading
        guard let discover = env.discover else {
            state = .error("Nicht mit vault-api verbunden.")
            return
        }
        do {
            let response = try await discover.suggestions(request)
            // Accumulate seen ids for subsequent reshuffles
            let newIds = ([response.libraryPick, response.discoverPick].compactMap { $0 } + response.alternatives)
                .map { $0.id }
            seenIds = Array(Set(seenIds + newIds))
            state = .loaded(response)
        } catch {
            state = .error(error.localizedDescription)
        }
    }

    @MainActor
    private func reshuffle(_ response: PickerResponse) async {
        await load(request: currentRequest())
    }

    // MARK: Playback helpers

    @MainActor
    private func playLibraryItem(_ pick: PickItem) async {
        guard let libraryId = pick.libraryId else { return }
        await playById(libraryId)
    }

    @MainActor
    private func playById(_ libraryId: String) async {
        guard let library = env.library,
              let base = try? await library.item(id: libraryId) else { return }
        playerItem = await env.playerItem(for: base, resume: base.resumePositionSeconds > 1)
    }
}

// MARK: - HeroCard

/// Large 16:9 backdrop card shown for a single pick.
private struct HeroCard: View {
    @Environment(AppEnvironment.self) private var env

    let pick: PickItem
    let kicker: String
    let kickerColor: Color
    let onPlay: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Backdrop / poster image
            ZStack(alignment: .bottomLeading) {
                let imageURL = pick.backdropUrl.flatMap { URL(string: $0) }
                             ?? pick.posterUrl.flatMap { URL(string: $0) }
                RemoteImage(url: imageURL)
                    .frame(maxWidth: .infinity)
                    .frame(height: 340)
                    .clipShape(RoundedRectangle(cornerRadius: Theme.cornerRadius))
                    .accessibilityHidden(true)

                LinearGradient(
                    colors: [.clear, Theme.bg.opacity(0.75)],
                    startPoint: .center,
                    endPoint: .bottom
                )
                .clipShape(RoundedRectangle(cornerRadius: Theme.cornerRadius))
            }

            VStack(alignment: .leading, spacing: 14) {
                // Kicker
                Text(kicker)
                    .font(.system(size: 15, weight: .heavy))
                    .kerning(2)
                    .foregroundStyle(kickerColor)
                    .padding(.top, 16)

                // Title + year
                Text(pick.title)
                    .font(.system(size: 36, weight: .bold))
                    .lineLimit(2)
                    .foregroundStyle(Theme.textPrimary)
                if let year = pick.year {
                    Text(String(year))
                        .font(.system(size: 20))
                        .foregroundStyle(Theme.textDim)
                }

                // Meta row: avatars + fear factor
                HStack(spacing: 12) {
                    avatarRow
                    if let fear = pick.fearFactor {
                        fearPill(fear)
                    }
                    if let rating = pick.communityRating {
                        Text("★ \(String(format: "%.1f", rating))")
                            .font(.system(size: 17, weight: .bold))
                            .foregroundStyle(Theme.textDim)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 4)
                            .overlay(
                                RoundedRectangle(cornerRadius: 6)
                                    .stroke(Theme.textDim.opacity(0.4), lineWidth: 1)
                            )
                    }
                }

                // Reason
                Text(pick.reason)
                    .font(.system(size: 20))
                    .foregroundStyle(Theme.textDim)
                    .lineLimit(3)
                    .fixedSize(horizontal: false, vertical: true)

                // CTA button
                ctaButton
                    .padding(.top, 8)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    // MARK: Avatar row

    private var avatarRow: some View {
        HStack(spacing: -8) {
            avatarCircle("J", color: Color(red: 232/255, green: 160/255, blue: 48/255))
            avatarCircle("T", color: Color(red: 140/255, green: 100/255, blue: 220/255))
        }
    }

    private func avatarCircle(_ letter: String, color: Color) -> some View {
        Circle()
            .fill(color)
            .frame(width: 36, height: 36)
            .overlay(
                Text(letter)
                    .font(.system(size: 16, weight: .bold))
                    .foregroundStyle(Theme.accentText)
            )
            .overlay(Circle().stroke(Theme.bg, lineWidth: 2))
    }

    private func fearPill(_ fear: Int) -> some View {
        HStack(spacing: 5) {
            Image(systemName: "moon.fill")
                .font(.system(size: 13, weight: .bold))
            Text("Gruselfaktor \(fear)")
                .font(.system(size: 15, weight: .bold))
        }
        .foregroundStyle(Theme.accentText)
        .padding(.horizontal, 10)
        .padding(.vertical, 5)
        .background(Theme.accent.opacity(0.85), in: Capsule())
    }

    // MARK: CTA button

    @ViewBuilder
    private var ctaButton: some View {
        if pick.isPlayable, let libraryId = pick.libraryId {
            Button {
                onPlay()
            } label: {
                Label("Abspielen", systemImage: "play.fill")
                    .font(.system(size: 24, weight: .bold))
                    .foregroundStyle(Theme.accentText)
                    .padding(.horizontal, 32)
                    .padding(.vertical, 14)
                    .background(Theme.accent, in: RoundedRectangle(cornerRadius: Theme.cornerRadius))
            }
            .buttonStyle(CardButtonStyle(scale: 1.06))
        } else {
            NavigationLink {
                RequestDetailView(item: pick.asRecommendationItem)
            } label: {
                Label("Anfragen", systemImage: "plus.circle.fill")
                    .font(.system(size: 24, weight: .bold))
                    .foregroundStyle(Theme.accent)
                    .padding(.horizontal, 32)
                    .padding(.vertical, 14)
                    .overlay(
                        RoundedRectangle(cornerRadius: Theme.cornerRadius)
                            .stroke(Theme.accent, lineWidth: 2)
                    )
            }
            .buttonStyle(CardButtonStyle(scale: 1.06))
        }
    }
}

