import AVFoundation

/// Loads and plays the short cold-start intro SFX. Uses the ambient audio
/// session (mix-with-others) so it never interrupts other audio and respects
/// the system volume; playback later sets its own `.playback` category.
@MainActor
final class IntroSound {
    private var players: [String: AVAudioPlayer] = [:]

    init() {
        let session = AVAudioSession.sharedInstance()
        try? session.setCategory(.ambient, options: [.mixWithOthers])
        try? session.setActive(true)
        for name in ["dial_spin", "unlock_clunk", "door_open"] {
            guard let url = Bundle.main.url(forResource: name, withExtension: "wav"),
                  let player = try? AVAudioPlayer(contentsOf: url) else { continue }
            player.prepareToPlay()
            players[name] = player
        }
    }

    func play(_ name: String, volume: Float = 1) {
        guard let player = players[name] else { return }
        player.currentTime = 0
        player.volume = volume
        player.play()
    }
}
