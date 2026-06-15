# Vault — tvOS Media Player

Private Jellyfin-Client für Apple TV mit eigener FFmpeg→VideoToolbox-Playback-Engine
für MKV/HEVC-Inhalte, die AVPlayer nicht abspielen kann.

**Stand: Milestones 1–3** — Jellyfin-Anbindung (Bibliothek, Fortsetzen, Fortschritt),
Browse-UI (Home mit Stage-Vorschau, Filme/Serien-Grid, Detail), Custom-Player
(HEVC/H.264 Hardware-Decode, AC3/EAC3/AAC-Audio, Seek ±10 s, Fortschrittsmeldung).

> **Architektur-Hinweis:** Das Projekt ist auf eine **API-First**-Zielarchitektur
> umgestellt — ein `vault-api`-Backend auf dem NAS orchestriert alle Dienste, die
> App spricht nur noch mit diesem einen Endpunkt. Der hier beschriebene
> direkte Jellyfin-Networking-Layer wird dabei zu einem dünnen `VaultClient`;
> **Player-Engine, UI und Models bleiben.** Volle Doku & Zielbild:
>
> - **[docs/README.md](docs/README.md)** — Überblick, Status, Lesereihenfolge fürs Review
> - **[docs/architecture-api-first.md](docs/architecture-api-first.md)** — Zielarchitektur + getroffene Entscheidungen
> - **[docs/implementation-current.md](docs/implementation-current.md)** — der aktuell gebaute Stand (Code-Doku)
> - **[Mockup/vault-mockup.html](Mockup/vault-mockup.html)** — Design-Mockup aller Screens (am Handy ansehbar)

## Build (auf dem Mac)

```bash
cd Vault
./scripts/generate-xcode-project.sh
```

Das Script prüft `xcodegen`, installiert es bei vorhandenem Homebrew automatisch,
generiert `Vault.xcodeproj` und öffnet das Projekt. Manuell entspricht das:

```bash
brew install xcodegen          # einmalig
cd Vault
xcodegen generate
open Vault.xcodeproj
```

1. Beim ersten Öffnen lädt SPM die FFmpegKit-xcframeworks (mehrere hundert MB, einmalig).
2. In *Signing & Capabilities* das eigene Team wählen (oder `DEVELOPMENT_TEAM` in `project.yml` setzen).
3. Ziel: **echtes Apple TV** bevorzugt — der Simulator verhält sich bei
   VideoToolbox/HEVC-Hardware-Decode nicht repräsentativ.
4. Build & Run → beim ersten Start Jellyfin-URL + Login eingeben.

Tests (`VaultTests`, reine Logik: DTO-Decoding, URL-Builder): ⌘U.

## Bekannte Iterationspunkte (erster Build)

Dieser Code wurde ohne Xcode geschrieben — Compile-Fehler bitte zurückmelden. Die
riskanten Stellen sind bewusst in einzelne Dateien isoliert:

| Risiko | Datei | Fallback |
|---|---|---|
| FFmpeg-Modulnamen (`import Libavformat` …) | `Player/FFmpegHelpers.swift` u. a. | `import FFmpegKit` als Umbrella probieren |
| Linking des `FFmpegKit`-Produkts | `project.yml` | stattdessen Produkte `Libavformat, Libavcodec, Libavutil, Libswresample, Libswscale, gnutls, hogweed, nettle, gmp` einzeln eintragen |
| AVPacket → CMSampleBuffer-Interop | `Player/VideoSampleFactory.swift` | — |
| C-Interop (Interrupt-Callback, Pointer) | `Player/Demuxer.swift` | — |
| Stream-Auth per HTTP-Header (`headers`-Option) | `Player/Demuxer.swift`, `StreamURLBuilder` | bei 401: `api_key`-Query-Param in `StreamURLBuilder` wieder anhängen |

## Sicherheit (bewusste Entscheidungen)

Vault ist ein **privater, sideloaded Client für die eigene Bibliothek** im
LAN/VPN — kein generischer Jellyfin-Client. Daraus folgen drei Tradeoffs:

- **Token nie in URLs.** Der Stream wird über die libavformat-`headers`-Option
  mit `X-Emby-Token` authentifiziert; API-Calls nutzen den `Authorization`-
  Header. Damit landet das Token nicht in Server-Access-Logs, Proxies oder
  Crash-Reports. (Jellyfin-Bild-Endpunkte sind standardmäßig anonym.)
- **ATS global offen** (`NSAllowsArbitraryLoads`), weil die Server-URL vom
  Nutzer frei eingegeben wird — Host-spezifische ATS-Ausnahmen sind bei
  dynamischen Hosts nicht möglich. HTTPS funktioniert und ist zu bevorzugen,
  wenn der Server es anbietet.
- **HTTP-Default** beim Eingeben einer URL ohne Schema, weil typische
  Heim-Setups (`192.168.x.x:8096`) kein TLS haben. Wer `https://` eintippt,
  bekommt TLS.

## Architektur

- `Vault/Networking`, `Vault/Models` — nur Foundation, testbar, kein UIKit/Libav.
- `Vault/UI` — SwiftUI, tvOS-Fokus-Engine, Design: `#0A0A0C` + Akzent `#E8A030`.
- `Vault/Player` — einziger Ort mit Libav-Imports. Demux (libavformat, eigener Thread)
  → Video: komprimierte `CMSampleBuffer` direkt in `AVSampleBufferDisplayLayer`
  (implizites VideoToolbox-HW-Decode) → Audio: libavcodec→PCM→`AVAudioEngine`.
  A/V-Sync: Audio ist Master-Clock, Video-`CMTimebase` wird darauf gezogen.

## Noch nicht enthalten (bewusst)

Radarr/Sonarr, Untertitel, DTS/TrueHD, Mehrkanal-/Passthrough-Audio, HDR-Handling,
Tonspur-Auswahl, Downloads-Screen, Transcoding-Fallback, App-Icon (für Dev-Build
nicht nötig).
