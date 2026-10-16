import SwiftUI

/// A line-wrapping layout that places word subviews along a row and wraps to a
/// new line when space runs out. When `isRTL` is true, rows are laid out from
/// the trailing edge so Hebrew reads right-to-left.
struct FlowLayout: Layout {
    var spacing: CGFloat = 8
    var lineSpacing: CGFloat = 28
    var isRTL: Bool = true

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout Void) -> CGSize {
        let maxWidth = proposal.width ?? .infinity
        let rows = computeRows(maxWidth: maxWidth, subviews: subviews)
        var totalHeight: CGFloat = 0
        for (index, row) in rows.enumerated() {
            let rowHeight = row.map { $0.1.height }.max() ?? 0
            totalHeight += rowHeight
            if index < rows.count - 1 { totalHeight += lineSpacing }
        }
        return CGSize(width: maxWidth == .infinity ? 0 : maxWidth, height: totalHeight)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout Void) {
        let rows = computeRows(maxWidth: bounds.width, subviews: subviews)
        var y = bounds.minY
        for row in rows {
            let rowHeight = row.map { $0.1.height }.max() ?? 0
            var cursor: CGFloat = 0
            for (subview, size) in row {
                let posX: CGFloat
                if isRTL {
                    posX = bounds.maxX - cursor - size.width
                } else {
                    posX = bounds.minX + cursor
                }
                subview.place(
                    at: CGPoint(x: posX, y: y),
                    anchor: .topLeading,
                    proposal: ProposedViewSize(size)
                )
                cursor += size.width + spacing
            }
            y += rowHeight + lineSpacing
        }
    }

    private func computeRows(maxWidth: CGFloat, subviews: Subviews) -> [[(LayoutSubview, CGSize)]] {
        var rows: [[(LayoutSubview, CGSize)]] = [[]]
        var x: CGFloat = 0
        for subview in subviews {
            let size = subview.sizeThatFits(.unspecified)
            if x + size.width > maxWidth, x > 0 {
                rows.append([])
                x = 0
            }
            rows[rows.count - 1].append((subview, size))
            x += size.width + spacing
        }
        return rows
    }
}
