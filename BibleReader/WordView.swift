import SwiftUI

/// A single Hebrew word. Holding it reveals the English gloss above and the
/// grammatical classification below, while signalling the parent to pause
/// audio. Releasing hides the annotation and resumes audio.
struct WordView: View {
    let word: InterlinearWord
    let isActive: Bool
    let onPressBegan: () -> Void
    let onPressEnded: () -> Void

    var body: some View {
        Text(word.heb)
            .font(.system(size: 34))
            .foregroundStyle(isActive ? Color.accentColor : .primary)
            .fixedSize()
            .padding(.horizontal, 2)
            .background(
                RoundedRectangle(cornerRadius: 6)
                    .fill(isActive ? Color.accentColor.opacity(0.12) : .clear)
            )
            .overlay(alignment: .top) {
                if isActive {
                    annotation(word.gloss)
                        .alignmentGuide(.top) { $0[.bottom] + 6 }
                }
            }
            .overlay(alignment: .bottom) {
                if isActive {
                    annotation(word.parseFull)
                        .alignmentGuide(.bottom) { $0[.top] - 6 }
                }
            }
            .contentShape(Rectangle())
            .gesture(holdGesture)
            .animation(.easeOut(duration: 0.12), value: isActive)
    }

    private func annotation(_ text: String) -> some View {
        Text(text)
            .font(.caption)
            .multilineTextAlignment(.center)
            .fixedSize(horizontal: false, vertical: true)
            .frame(width: 160)
            .padding(.vertical, 5)
            .padding(.horizontal, 8)
            .background(
                RoundedRectangle(cornerRadius: 8)
                    .fill(Color(.secondarySystemBackground))
                    .shadow(radius: 3, y: 1)
            )
            .environment(\.layoutDirection, .leftToRight)
    }

    /// Fires `onPressBegan` once the hold is recognized and `onPressEnded`
    /// when the finger lifts. The short minimum duration lets vertical scroll
    /// gestures win first, so the list still scrolls normally.
    private var holdGesture: some Gesture {
        LongPressGesture(minimumDuration: 0.18)
            .onEnded { _ in onPressBegan() }
            .sequenced(before: DragGesture(minimumDistance: 0))
            .onEnded { _ in onPressEnded() }
    }
}
