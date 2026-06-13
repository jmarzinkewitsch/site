# Vault — Implementierung (aktueller Stand)

Dokumentiert den heute geschriebenen Code (Milestones 1–3). Geschrieben ohne
Xcode; **noch nie kompiliert oder auf Hardware gelaufen** — die Risikostellen
sind unten markiert. Bezug zur Zielarchitektur: siehe
[architecture-api-first.md](architecture-api-first.md).

## Modul-Karte

```
Vault/Vault/
  App/
    VaultApp.swift           App-Entry; zeigt Onboarding oder RootTabView
    AppEnvironment.swift     Composition Root; baut Client/Services aus Settings
    Theme.swift              Farben, Maße, Format-Helfer (Laufzeit, Badges)
  Models/                    reine Foundation-DTOs (Codable), kein UIKit/Libav
    BaseItem.swift           Jellyfin-Item + abgeleitete Felder (Resume, Badges)
    MediaSource.swift, UserItemData.swift, QueryResult.swift, …
    PlaybackReports.swift    Start/Progress/Stop-DTOs, Ticks-Umrechnung
  Networking/Jellyfin/       Foundation-only, testbar
    JellyfinClient.swift     actor; Token-Auth (MediaBrowser-Header), GET/POST
    AuthService.swift        Login / Token-Validierung
    LibraryService.swift     Resume, NextUp, Latest, Items, Seasons, Episodes
    PlaybackReporter.swift   Fire-and-forget Start/Progress/Stop
    ImageURLBuilder.swift, StreamURLBuilder.swift
  Settings/
    ServerSettings.swift     UserDefaults; URL-Normalisierung, deviceId
    SettingsView.swift       Onboarding/Login
  UI/
    Components/              RemoteImage, PosterCard, ContinueWatchingCard,
                             MediaShelf, StageView, FocusEffects
    Screens/                 RootTabView, Home, LibraryGrid, ItemDetail (+ VMs)
  Player/                    EINZIGER Ort mit Libav-Imports
    PlayerItem.swift, PlayerViewModel.swift, PlayerScreen.swift,
    VideoLayerView.swift, PlayerOverlayView.swift
    Engine/
      FFmpegHelpers.swift, Demuxer.swift, PacketQueue.swift,
      VideoFormatDescFactory.swift, AnnexBConverter.swift,
      VideoSampleFactory.swift, VideoRenderer.swift,
      PCMRingBuffer.swift, AudioDecoder.swift, AudioRenderer.swift,
      PlaybackEngine.swift
```

Trennung: `Models`/`Networking` sind reine Foundation (gut testbar), `UI` ist
SwiftUI, `Player` kapselt alles C/Libav. Diese Grenzen bleiben auch nach dem
API-First-Umbau bestehen — nur `Networking/Jellyfin/*` wird durch einen dünnen
`VaultClient` ersetzt.

## Player-Engine (der Kern)

Eigene Pipeline, weil `AVPlayer` viele MKV/HEVC/EAC3-Kombinationen nicht
abspielt. Idee: **nicht** in Software dekodieren, sondern die komprimierten
Frames als `CMSampleBuffer` in einen `AVSampleBufferDisplayLayer` geben →
VideoToolbox dekodiert implizit in Hardware. Audio läuft über libavcodec.

### Threads

| Thread | Aufgabe |
|---|---|
| Engine-Queue (seriell) | State-Machine, open/seek/play/pause, Sync-Timer |
| Demux-Thread | `av_read_frame`-Schleife + `av_seek_frame` (einziger Owner von libavformat nach open) |
| Audio-Thread | Packet → libavcodec → swresample → Stereo-PCM → Ringbuffer |
| Video-Feed-Queue | Packet → `CMSampleBuffer` → Display-Layer |
| Audio-Render-Callback | Ringbuffer → Lautsprecher; liefert die Audio-Uhr |

### Clocking (A/V-Sync)

Audio ist die **Master-Clock**: Der Render-Callback schreibt die PTS der
gerade ausgegebenen Sample (latenz-kompensiert) als Audio-Uhr. Ein 4-Hz-Timer
auf der Engine-Queue zieht die `CMTimebase` des Display-Layers darauf (Korrektur
nur bei Drift > 100 ms). Ohne Audiospur läuft die Timebase frei.

### Seek-Protokoll (race-frei)

1. `seek(to:)` erhöht die **Generation** und parkt die Anforderung.
2. Demux-Thread seekt, flusht beide Queues, übergibt an `finishSeek`
   (Engine-Queue) und **parkt auf einer Semaphore**.
3. `finishSeek` setzt Ring/Uhr/Layer zurück, danach Signal → Demux liest mit
   neuer Generation weiter.
4. Pakete tragen ihre Generation aus dem **Enqueue**-Zeitpunkt; Audio- und
   Video-Konsument verwerfen veraltete Pakete. So kann kein altes Paket nach
   dem Seek durchrutschen.

### Lifecycle / Stop (kein Use-after-free)

`stop()` setzt das Cancel-Token (bricht blockierendes `av_read_frame` ab),
schließt die Queues, **wartet per Semaphore auf das Auslaufen von Demux- und
Audio-Thread** und schließt erst danach den `AVFormatContext`. Damit kann der
Kontext nicht abgebaut werden, während noch ein libav-Call läuft.

### Audio-Fallback sichtbar

Schlägt das Audio-Setup fehl (Codec/Session), läuft das Video weiter und ein
`audioUnavailable`-Event setzt im Overlay das „Ohne Ton"-Badge — kein stilles
Verschlucken.

### Format-Handling

`VideoFormatDescFactory` baut die `CMFormatDescription` aus avcC/hvcC; für
Annex-B-Streams sammelt `AnnexBConverter` die Parameter-Sets inband und setzt
4-Byte-Längenpräfixe. `VideoSampleFactory` erzeugt daraus die Sample-Buffer
(inkl. NOT-SYNC-Attachment für Nicht-Keyframes).

## Jellyfin-Anbindung

`JellyfinClient` (actor) mit Token-Auth über den `MediaBrowser`-Header; Stream-
Auth bewusst über einen HTTP-Header statt `api_key` in der URL (Token nicht in
Logs). `LibraryService` deckt Resume/NextUp/Latest/Items/Seasons/Episodes ab,
`PlaybackReporter` meldet Start/Progress(10 s)/Stop — Stop wird bei `.ended`/
`.failed` idempotent sofort gesendet.

## Tests (`VaultTests`)

Reine Logik, ohne Hardware/Libav-Laufzeit:

- `JellyfinDTOTests` — DTO-Decoding, abgeleitete Felder, Ticks.
- `URLBuilderTests` — Stream-/Image-URLs, Auth-Header (Token nicht in URL).
- `PCMRingBufferTests` — Wraparound, Teil-Writes, PTS-Fortschreibung, Reset,
  Zero-Padding.
- `PacketQueueTests` — FIFO, Byte-Limit, Flush, Close-Wakeups, Generation-Tags.

Nicht getestet: Player-Lifecycle als Ganzes (braucht libav/tvOS-Laufzeit) —
bewusst zurückgestellt, bis die Engine einmal auf Hardware lief.

## Risiken beim ersten Build

| Risiko | Datei | Fallback |
|---|---|---|
| FFmpeg-Modulnamen (`import Libavformat` …) | `Player/Engine/FFmpegHelpers.swift` u. a. | `import FFmpegKit` als Umbrella |
| Linking des `FFmpegKit`-Produkts | `project.yml` | Libav*-Produkte einzeln eintragen |
| AVPacket → CMSampleBuffer | `Player/Engine/VideoSampleFactory.swift` | — |
| C-Interop (Callback, Pointer, swr) | `Demuxer.swift`, `AudioDecoder.swift` | — |

## Verhältnis zur Zielarchitektur (API-First)

- **Wird ersetzt:** `Networking/Jellyfin/*` → ein dünner `VaultClient`, der nur
  `vault-api` spricht (Bearer-Token). DTO-Decoding wandert serverseitig.
- **Bleibt unverändert:** die komplette **Player-Engine** (sie braucht nur
  „Stream-URL + Header", künftig aus `/stream/{id}`), die **UI**, das **Theme**
  und die SwiftUI-Models (werden schlanker).
- **Neu, serverseitig statt in Swift:** Empfehlungs-Engine (`recommender.py`),
  Radarr/Sonarr/Lidarr-, TMDB-, OMDb-, Roon-Anbindung.
