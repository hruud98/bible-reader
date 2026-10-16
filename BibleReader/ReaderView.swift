import SwiftUI

struct ReaderView: View {
    private let verses = JonahData.versesForChapter1()
    @StateObject private var audio = AudioManager(
        url: URL(string: "https://mechon-mamre.org/mp3/t1701.mp3")!
    )

    /// The word currently being held, if any.
    @State private var activeWordID: UUID?
    /// Whether audio was playing when the current hold began.
    @State private var wasPlayingBeforeHold = false

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .trailing, spacing: 26) {
                    ForEach(verses, id: \.verse) { verse in
                        verseView(verse.verse, words: verse.words)
                    }
                }
                .padding(.horizontal, 20)
                .padding(.vertical, 28)
            }
            .navigationTitle("יוֹנָה א")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        audio.toggle()
                    } label: {
                        Image(systemName: audio.isPlaying ? "pause.circle.fill" : "play.circle.fill")
                            .font(.title2)
                    }
                }
            }
        }
    }

    @ViewBuilder
    private func verseView(_ number: Int, words: [InterlinearWord]) -> some View {
        FlowLayout(spacing: 10, lineSpacing: 34, isRTL: true) {
            ForEach(words) { word in
                WordView(
                    word: word,
                    isActive: activeWordID == word.id,
                    onPressBegan: { beginHold(on: word) },
                    onPressEnded: { endHold() }
                )
                .zIndex(activeWordID == word.id ? 1 : 0)
            }
            // Verse number rendered as the first (right-most) element.
            Text("\(number)")
                .font(.footnote)
                .foregroundStyle(.secondary)
                .baselineOffset(6)
        }
        .environment(\.layoutDirection, .rightToLeft)
    }

    private func beginHold(on word: InterlinearWord) {
        wasPlayingBeforeHold = audio.isPlaying
        if audio.isPlaying {
            audio.pause()
        }
        activeWordID = word.id
    }

    private func endHold() {
        activeWordID = nil
        if wasPlayingBeforeHold {
            audio.resume()
        }
        wasPlayingBeforeHold = false
    }
}
