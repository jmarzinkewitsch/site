import SwiftUI

/// 2:3 poster card with title and year, amber ring + scale on focus.
struct PosterCard: View {
    let item: BaseItemDto
    let imageURL: URL?
    var width: CGFloat = Theme.posterWidth

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            ZStack(alignment: .bottomLeading) {
                RemoteImage(url: imageURL)
                    .frame(width: width, height: width * Theme.posterAspectRatio)
                    .accessibilityHidden(true)

                if item.watchedFraction > 0 {
                    GeometryReader { geo in
                        Rectangle()
                            .fill(Theme.accent)
                            .frame(width: geo.size.width * item.watchedFraction, height: 6)
                            .frame(maxHeight: .infinity, alignment: .bottom)
                    }
                }

                if item.isPlayed {
                    Image(systemName: "checkmark.circle.fill")
                        .font(.system(size: 28, weight: .bold))
                        .foregroundStyle(Theme.textPrimary)
                        .shadow(radius: 6)
                        .padding(12)
                        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topTrailing)
                        .accessibilityHidden(true)
                }
            }
            .frame(width: width, height: width * Theme.posterAspectRatio)
            .clipShape(RoundedRectangle(cornerRadius: Theme.cornerRadius))
            .modifier(FocusRing())
            VStack(alignment: .leading, spacing: 3) {
                Text(item.name ?? "—")
                    .font(.system(size: 22, weight: .semibold))
                    .lineLimit(1)
                    .foregroundStyle(Theme.textPrimary)
                if let year = item.productionYear {
                    Text(String(year))
                        .font(.system(size: 18))
                        .foregroundStyle(Theme.textDim)
                }
            }
            .frame(width: width, alignment: .leading)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(accessibilityLabel)
    }

    private var accessibilityLabel: String {
        var parts = [item.name ?? "Unbenannt"]
        if let year = item.productionYear { parts.append(String(year)) }
        if item.isPlayed {
            parts.append("gesehen")
        } else if item.watchedFraction > 0 {
            parts.append("\(Int(item.watchedFraction * 100)) Prozent gesehen")
        }
        return parts.joined(separator: ", ")
    }
}
