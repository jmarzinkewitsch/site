import SwiftUI

/// Codec/format chips (e.g. "4K", "HEVC", "EAC3 5.1") shown under the title on
/// the Home stage and the detail header. Extracted so both render identically.
struct BadgeRow: View {
    let badges: [String]

    var body: some View {
        HStack(spacing: 18) {
            ForEach(badges, id: \.self) { badge in
                Text(badge)
                    .font(.system(size: 17, weight: .bold))
                    .foregroundStyle(Theme.textDim)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 4)
                    .overlay(
                        RoundedRectangle(cornerRadius: 7)
                            .stroke(Theme.textDim.opacity(0.5), lineWidth: 1)
                    )
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(badges.isEmpty ? "" : "Format: \(badges.joined(separator: ", "))")
    }
}
