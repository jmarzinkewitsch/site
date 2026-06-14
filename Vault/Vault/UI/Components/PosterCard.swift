import SwiftUI

/// 2:3 poster card with title and year, amber ring + scale on focus.
struct PosterCard: View {
    let item: BaseItemDto
    let imageURL: URL?
    var width: CGFloat = Theme.posterWidth

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            RemoteImage(url: imageURL)
                .frame(width: width, height: width * Theme.posterAspectRatio)
                .clipShape(RoundedRectangle(cornerRadius: Theme.cornerRadius))
                .modifier(FocusRing())
                .accessibilityHidden(true)
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
        let name = item.name ?? "Unbenannt"
        if let year = item.productionYear { return "\(name), \(year)" }
        return name
    }
}
