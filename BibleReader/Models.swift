import Foundation

/// A single Hebrew word from the interlinear, with its English gloss and
/// grammatical parsing taken from the BibleHub interlinear of Jonah.
struct InterlinearWord: Identifiable, Decodable {
    let id = UUID()
    let verse: Int
    let heb: String
    let translit: String
    let gloss: String
    /// Abbreviated parsing code, e.g. "V-Qal-CImperf-3ms".
    let parse: String
    /// Full human-readable grammatical classification.
    let parseFull: String

    private enum CodingKeys: String, CodingKey {
        case verse, heb, translit, gloss, parse, parseFull
    }
}

/// Loads the bundled Jonah chapter data.
enum JonahData {
    static func loadChapter1() -> [InterlinearWord] {
        guard let url = Bundle.main.url(forResource: "jonah1", withExtension: "json"),
              let data = try? Data(contentsOf: url),
              let words = try? JSONDecoder().decode([InterlinearWord].self, from: data)
        else {
            return []
        }
        return words
    }

    /// Words grouped into verses, preserving order.
    static func versesForChapter1() -> [(verse: Int, words: [InterlinearWord])] {
        let all = loadChapter1()
        var result: [(Int, [InterlinearWord])] = []
        for word in all {
            if let last = result.last, last.0 == word.verse {
                result[result.count - 1].1.append(word)
            } else {
                result.append((word.verse, [word]))
            }
        }
        return result.map { (verse: $0.0, words: $0.1) }
    }
}
