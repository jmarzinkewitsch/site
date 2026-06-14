import SwiftUI

/// Poster card for the "Für dich" shelves: artwork with a status pill, score
/// badges, title and the recommendation reason underneath.
struct RecommendationCard: View {
    let item: RecommendationItem
    let imageURL: URL?
    var isRequesting: Bool = false

    private let width = Theme.posterWidth

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            ZStack(alignment: .topTrailing) {
                RemoteImage(url: imageURL)
                    .frame(width: width, height: width * Theme.posterAspectRatio)
                    .clipShape(RoundedRectangle(cornerRadius: Theme.cornerRadius))
                    .modifier(FocusRing())
                    .accessibilityHidden(true)
                statusPill.padding(8)
            }

            scores

            Text(item.title)
                .font(.system(size: 22, weight: .semibold))
                .lineLimit(1)
                .foregroundStyle(Theme.textPrimary)

            Text(item.reason)
                .font(.system(size: 17))
                .lineLimit(2)
                .foregroundStyle(Theme.textDim)
                .frame(width: width, height: 46, alignment: .topLeading)
        }
        .frame(width: width, alignment: .leading)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(accessibilityLabel)
    }

    @ViewBuilder
    private var statusPill: some View {
        if isRequesting {
            pill { ProgressView().tint(Theme.accentText) }
        } else if item.isRequestable {
            pill {
                Label("Anfragen", systemImage: "plus.circle.fill")
                    .labelStyle(.titleAndIcon)
            }
        }
    }

    private func pill<Content: View>(@ViewBuilder _ content: () -> Content) -> some View {
        content()
            .font(.system(size: 15, weight: .bold))
            .foregroundStyle(Theme.accentText)
            .padding(.horizontal, 10)
            .padding(.vertical, 5)
            .background(Theme.accent, in: Capsule())
    }

    @ViewBuilder
    private var scores: some View {
        HStack(spacing: 8) {
            if let imdb = item.communityRating {
                scoreBadge("★ \(String(format: "%.1f", imdb))")
            }
            if let rt = item.criticRating {
                scoreBadge("RT \(Int(rt))%")
            }
        }
        .frame(height: 22)
    }

    private func scoreBadge(_ text: String) -> some View {
        Text(text)
            .font(.system(size: 15, weight: .bold))
            .foregroundStyle(Theme.textDim)
            .padding(.horizontal, 8)
            .padding(.vertical, 3)
            .overlay(
                RoundedRectangle(cornerRadius: 6)
                    .stroke(Theme.textDim.opacity(0.5), lineWidth: 1)
            )
    }

    private var accessibilityLabel: String {
        var parts = [item.title]
        if let year = item.year { parts.append(String(year)) }
        parts.append(item.isPlayable ? "abspielbar" : "anfragbar")
        parts.append(item.reason)
        return parts.joined(separator: ", ")
    }
}
