# Auto-Skip: Intros & Abspann automatisch überspringen

**Datum:** 2026-06-21
**Status:** Design, freigegeben — Umsetzung folgt

## Ziel

Intro- und Outro-Segmente (vom Jellyfin-Intro-Skipper-Plugin, bereits als
`PlayerItem.segments` im Player verfügbar) werden **automatisch** übersprungen,
statt nur den manuellen Button anzubieten. Per Settings-Schalter abschaltbar
(Default an). Beim Auto-Skip ein kurzer Hinweis; kein erneutes Auto-Skip, wenn
man bewusst in ein bereits übersprungenes Segment zurückspult.

## Verhalten

- **Umfang:** Intro **und** Abspann (outro) werden auto-übersprungen. Auto-Skip
  des Abspanns springt ans Segment-Ende → löst regulär die „nächste Folge"-Logik
  aus (gewollt fürs Bingen).
- **Auslöser:** Sobald die Wiedergabe in ein Segment läuft (Progress-Tick), wird
  einmalig ans Segment-Ende gesprungen.
- **Re-Skip-Schutz:** Jedes Segment wird höchstens **einmal** automatisch
  übersprungen. Spult man manuell zurück hinein, passiert nichts — und der
  manuelle „überspringen"-Button erscheint dort wieder.
- **Hinweis:** Kurzer Toast „Intro übersprungen" / „Abspann übersprungen"
  (~1,8 s).
- **Schalter aus:** Verhalten exakt wie heute (nur manueller Button).

## Umsetzung

### `PlayerViewModel`
- `private var autoSkippedSegments: Set<StreamSegment> = []` (StreamSegment ist
  `Hashable`; pro Player-Instanz frisch).
- `autoSkipEnabled`: liest `UserDefaults.standard` für Key `autoSkipSegments`
  (Default `true`, wenn nicht gesetzt).
- Im `handle(_:)`-Fall `.time(seconds)` nach `currentSeconds = seconds` →
  `maybeAutoSkip()`.
- `maybeAutoSkip()`: guard `autoSkipEnabled`, `!isScrubbing`; wenn
  `activeSkipSegment` gesetzt und nicht in `autoSkippedSegments` → einfügen,
  `engine.seek(to: segment.end)`, `lastAutoSkipMessage` setzen (+ Auto-Clear nach
  ~1,8 s).
- `var lastAutoSkipMessage: String?` (observable) für den Toast.
- `var shouldShowSkipButton: Bool`: `false` wenn kein aktives Segment; bei
  ausgeschaltetem Auto-Skip `true`; bei eingeschaltetem nur `true`, wenn das
  aktive Segment schon auto-übersprungen wurde (Rückspul-Fall).

### `PlayerScreen`
- `skipButton` an `model.shouldShowSkipButton` knüpfen (statt
  `activeSkipSegment != nil`).
- Transienter Toast, wenn `model.lastAutoSkipMessage != nil`.

### `SettingsView`
- `@AppStorage("autoSkipSegments") private var autoSkipSegments = true`.
- Toggle „Intro & Abspann automatisch überspringen" in der Sektion
  „Personalisierung".

## Nicht im Scope
- Eigene Auto-Skip-Regeln pro Segmenttyp (intro vs. outro getrennt schaltbar).
- „Recap"/„Preview"-Segmenttypen (API mappt nur intro/outro).

## Verifikation
1. Serie mit Intro/Abspann: Intro wird automatisch übersprungen, kurzer Hinweis;
   am Episodenende springt der Abspann-Skip in die „nächste Folge".
2. Schalter aus → nur manueller Button, wie zuvor.
3. Ins übersprungene Intro zurückspulen → kein erneutes Auto-Skip, Button da.
