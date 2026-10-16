import AVFoundation
import Foundation

/// Streams the Hebrew audio for a chapter and supports immediate pause/resume
/// so a word can be inspected while holding it.
final class AudioManager: ObservableObject {
    @Published private(set) var isPlaying = false

    private var player: AVPlayer?
    private let url: URL

    init(url: URL) {
        self.url = url
        configureSession()
    }

    private func configureSession() {
        #if os(iOS)
        try? AVAudioSession.sharedInstance().setCategory(.playback, mode: .spokenAudio)
        try? AVAudioSession.sharedInstance().setActive(true)
        #endif
    }

    /// Starts playback from the beginning if not already playing.
    func play() {
        if player == nil {
            player = AVPlayer(url: url)
        }
        player?.play()
        isPlaying = true
    }

    /// Pauses immediately, retaining the current position for resume.
    func pause() {
        player?.pause()
        isPlaying = false
    }

    /// Resumes from the paused position.
    func resume() {
        player?.play()
        isPlaying = true
    }

    func toggle() {
        isPlaying ? pause() : (player == nil ? play() : resume())
    }

    func stop() {
        player?.pause()
        player?.seek(to: .zero)
        isPlaying = false
    }
}
