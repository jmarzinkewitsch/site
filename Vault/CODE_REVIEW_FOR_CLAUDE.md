# Code Review für Claude

Stand: statisches Review des Repositories `/workspace/site`, Fokus auf `Vault` tvOS/Jellyfin-Client und Custom-Playback-Engine.

Ziel dieses Dokuments: Die folgenden Punkte sind als konkrete Review-Kommentare formuliert, damit Claude sie direkt nacheinander abarbeiten, bewerten oder als Issues übernehmen kann.

## Kurzfazit

Die Architektur ist für einen frühen Milestone gut getrennt: Foundation-only Jellyfin-Layer, SwiftUI UI und ein isolierter Custom-Player mit FFmpeg/VideoToolbox-Pfad. Der riskanteste Teil ist erwartungsgemäß nicht die UI, sondern die Thread-/Lifecycle-Steuerung des Players.

Inhaltlich sollten vor allem diese Themen kritisch geprüft werden:

1. Stop-/Close-Races im Player.
2. Seek-Races zwischen alter und neuer Packet-Generation.
3. Token-Handling in Stream-URLs.
4. Silent Audio-Fallback ohne sichtbare Diagnose.
5. Playback-Reporting nach Playback-Ende.
6. Fehlende Tests für Queue/Ringbuffer/Player-Lifecycle.

---

## 1. Hoch: `stop()` kann `AVFormatContext` schließen, während der Demux-Thread noch liest

### Betroffene Stellen

- `Vault/Vault/Player/Engine/PlaybackEngine.swift`
  - `stop()` setzt Cancel-Token, schließt Queues und ruft später `demuxer.close()` auf.
  - `demuxLoop()` kann parallel noch in `demuxer.readPacket()` / `av_read_frame` laufen.
- `Vault/Vault/Player/Engine/Demuxer.swift`
  - `close()` ruft direkt `avformat_close_input(&context)` auf.

### Problem

`PlaybackEngine.stop()` beendet den Demux-Thread nicht synchron und hält keinen Thread-Handle, über den ein Join möglich wäre. Dadurch kann `demuxer.close()` auf der Engine-Queue ausgeführt werden, während `demuxLoop()` noch aktiv ist oder gerade aus `av_read_frame` zurückkehrt.

### Risiko

Seltene, schwer reproduzierbare Crashes beim Verlassen des Players, besonders bei:

- langsamen Jellyfin-Servern,
- Netzwerkabbrüchen,
- App-Hintergrund/Foreground-Wechseln auf tvOS,
- schnellem Öffnen und Schließen des Players.

### Empfehlung

Claude sollte prüfen und ggf. umsetzen:

- Demux-Thread als Property halten.
- Beim Stop:
  1. Cancel setzen.
  2. Queues schließen/wecken.
  3. Demux-Thread kontrolliert auslaufen lassen.
  4. Erst danach `avformat_close_input` ausführen.
- Alternativ: Alle `Demuxer`-Operationen strikt auf einem einzigen Owner-Thread serialisieren und `close` nie parallel zu `readPacket`/`seek` zulassen.

---

## 2. Hoch: Seek-Race kann alte Audio-/Video-Pakete nach dem Seek übernehmen

### Betroffene Stellen

- `Vault/Vault/Player/Engine/PlaybackEngine.swift`
  - `seek(to:)` erhöht `generation` sofort und setzt danach `pendingSeek`.
  - `demuxLoop()` führt den eigentlichen Seek und Queue-Flush später aus.
  - `audioLoop()` liest `generation` erst nach dem Pop aus der Queue.
  - `nextVideoSample()` hat gar keinen Generation-Check.

### Problem

Zwischen Seek-Anforderung und tatsächlichem Queue-Flush können alte Pakete noch aus Audio-/Video-Queue konsumiert werden.

Beim Audio-Pfad ist besonders kritisch: Die Generation wird nach dem Pop gelesen. Ein altes Paket kann also nach einer Seek-Anforderung gepoppt werden und fälschlich als Paket der neuen Generation gelten.

Beim Video-Pfad gibt es keinen entsprechenden Schutz; alte Video-Pakete können noch zu `CMSampleBuffer`s werden.

### Risiko

- kurze alte Audio-Schnipsel nach Seek,
- falsche Frames direkt nach Seek,
- Decoder-/Timebase-Störungen,
- instabiles Verhalten bei wiederholtem `±10s`-Seeking.

### Empfehlung

Claude sollte prüfen und ggf. umsetzen:

- Pakete beim Enqueue mit einer Generation taggen, nicht erst beim Pop.
- Queue-Typ ggf. auf Wrapper wie `QueuedPacket(packet:generation:)` erweitern.
- Während `state == .seeking` Audio-/Video-Popper blockieren oder Samples verwerfen.
- Video denselben Generation-Schutz geben wie Audio.
- Seek-Sequenz klarer machen: Pause/hold clocks → Flush queues → Flush decoders → Seek demuxer → neue Generation aktivieren → Buffering.

---

## 3. Hoch/Mittel: Jellyfin-Token wird als `api_key` in die Stream-URL geschrieben

### Betroffene Stellen

- `Vault/Vault/Networking/Jellyfin/StreamURLBuilder.swift`
  - `directStream` setzt `api_key={token}` als Query-Parameter.
- `Vault/Vault/Settings/ServerSettings.swift`
  - fehlendes Scheme wird automatisch zu `http://` ergänzt.
- `Vault/project.yml`
  - `NSAllowsArbitraryLoads: true` ist global gesetzt.

### Problem

Das Token landet in der URL. URLs werden häufig geloggt oder in Debug-Ausgaben, Proxies, Server-Access-Logs und Crash-Reports sichtbar.

Die Entscheidung ist technisch nachvollziehbar, weil libavformat hier keine Custom-Headers sendet. Trotzdem ist es ein starker Security-Tradeoff, vor allem zusammen mit HTTP-Default und global deaktiviertem ATS.

### Risiko

- Token-Leak über Logs oder Diagnosedaten.
- Token-Leak bei HTTP im LAN/VPN.
- Sicherheitsentscheidung ist aktuell nicht zentral dokumentiert oder konfigurierbar.

### Empfehlung

Claude sollte prüfen:

- Können FFmpeg/libavformat-Options wie `headers` genutzt werden, um Authorization/Header statt Query-Token zu senden?
- Falls Query-Token bleibt: README/Settings klar als bewusste private-LAN-Entscheidung dokumentieren.
- ATS nicht global öffnen, sondern möglichst hostspezifisch oder per Dev-Konfiguration.
- Optional HTTPS bevorzugen und HTTP explizit bestätigen lassen.

---

## 4. Mittel: Audio-Fehler werden geschluckt, Player spielt potenziell stumm

### Betroffene Stellen

- `Vault/Vault/Player/Engine/PlaybackEngine.swift`
  - Audio-Setup ist best-effort; Fehler im Catch-Block werden verworfen.
  - `audioRenderer.start()` wird mit `try?` aufgerufen.
- `Vault/README.md`
  - README nennt AC3/EAC3/AAC-Audio als unterstützten Milestone-Umfang.

### Problem

Wenn Decoder, Ringbuffer, Resampling oder `AVAudioSession` fehlschlagen, wird Audio deaktiviert, aber der Fehler wird weder sichtbar noch gemeldet.

### Risiko

- Nutzer sehen Video ohne Ton und wissen nicht warum.
- Entwickler verlieren wichtige Diagnoseinformationen.
- Reale Codec-/AudioSession-Probleme wirken wie Content-Probleme.

### Empfehlung

Claude sollte prüfen und ggf. umsetzen:

- Audio-Setup-Fehler mindestens als `PlayerEvent` oder Debug-Log melden.
- UI-Warnung im Overlay: „Video wird ohne Ton abgespielt“.
- Zwischen „Audio unsupported“ und „Audio setup failed“ unterscheiden.
- `try? audioRenderer.start()` vermeiden oder Fehler sichtbar machen.

---

## 5. Mittel: Playback-Reporting läuft nach `.ended` weiter, bis der Screen geschlossen wird

### Betroffene Stellen

- `Vault/Vault/Player/PlayerViewModel.swift`
  - `reportTask` sendet alle 10 Sekunden Progress, solange der Task nicht gecancelt ist.
  - `stopped` wird erst in `shutdown()` gesendet.

### Problem

Wenn Playback endet, aber der Player-Screen offen bleibt, läuft die Reporting-Loop weiter und meldet den Zustand als nicht-playing/paused. Ein sauberer `Stopped`-Report kommt erst beim Verlassen des Screens.

### Risiko

- Jellyfin-Session bleibt länger aktiv als nötig.
- Resume-/Watched-State kann verzögert oder falsch wirken.
- Aktive Sessions auf dem Server sind ungenau.

### Empfehlung

Claude sollte prüfen und ggf. umsetzen:

- Bei Engine-State `.ended` sofort `stopped` senden und `reportTask` beenden.
- Bei `.failed` ebenfalls Reporting sauber schließen oder Fehler separat behandeln.
- Idempotenz sicherstellen, damit `shutdown()` später nicht doppelt stoppt.

---

## 6. Mittel/Niedrig: Tests decken die riskantesten Komponenten nicht ab

### Betroffene Stellen

- `Vault/VaultTests/URLBuilderTests.swift`
- `Vault/VaultTests/JellyfinDTOTests.swift`

### Problem

Die vorhandenen Tests decken DTO-Decoding, URL-Builder, Auth-Header und Tick-Konvertierung ab. Die riskanten Player-Komponenten sind nicht getestet.

### Fehlende Testbereiche

- `PacketQueue`
  - `push`, `pop(wait:)`, `flush`, `close`, Byte-Limits, Wakeups.
- `PCMRingBuffer`
  - Partial Writes, Wraparound, Reset, PTS-Fortschreibung, Zero Padding.
- Player-Lifecycle
  - Open → Buffering → Playing → Seek → Ended/Stopped.
- Reporting-Lifecycle
  - Started → Progress → Ended/Stopped.

### Empfehlung

Claude sollte zuerst Tests für kleine, reine Komponenten ergänzen:

1. `PCMRingBuffer` ohne AVFoundation/FFmpeg-Abhängigkeit testen.
2. `PacketQueue` mit kontrollierten Fake-/Mock-Packets oder dünner Abstraktion testbarer machen.
3. Player-Lifecycle abstrahieren, damit State-Übergänge ohne echte libav/tvOS-Hardware testbar werden.

---

## Inhaltliche Challenges

### Silent Fallback vs. Medienplayer-Erwartung

Für einen Medienplayer ist „Video läuft, Audio fehlt“ kein nebensächlicher Zustand. Falls Audio bewusst best-effort ist, sollte das in der UI sichtbar werden.

### DirectStream-only Scope

Der aktuelle Scope ist DirectStream-only. Das ist für eine private, kontrollierte Jellyfin-Library okay. Für einen robusten Jellyfin-Client fehlen aber bewusst wichtige Themen:

- Transcoding-Fallback,
- Untertitel,
- Tonspur-Auswahl,
- DTS/TrueHD,
- HDR-Handling,
- Mehrkanal-/Passthrough-Audio.

Claude sollte klären, ob das Produktziel „optimiert für die eigene Library“ oder „generischer Jellyfin-Client“ ist. Davon hängen Prioritäten stark ab.

### Security-Entscheidungen zentralisieren

HTTP-Default, ATS arbitrary loads und Query-Token sind einzeln nachvollziehbar, aber gemeinsam riskant. Diese Entscheidungen sollten zentral dokumentiert und möglichst konfigurierbar sein.

---

## Priorisierte To-do-Liste für Claude

1. Demuxer-/Stop-Lifecycle racefrei machen.
2. Seek-Generation sauber auf Audio und Video anwenden.
3. Audio-Fehler sichtbar machen.
4. Playback-Reporting bei `.ended`/`.failed` sauber abschließen.
5. Token-in-URL-Ansatz überprüfen oder dokumentieren.
6. Unit-Tests für `PCMRingBuffer` und `PacketQueue` ergänzen.
