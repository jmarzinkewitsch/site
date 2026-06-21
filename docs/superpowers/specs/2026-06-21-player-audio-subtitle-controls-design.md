# Player: Audio- & Untertitel-Steuerung (tvOS)

**Datum:** 2026-06-21
**Status:** Design, bereit für Implementierungsplan

## Problem

Auf der Abspiel-Ansicht lassen sich die Audio- und Untertitel-Buttons nicht
öffnen: ein Klick/Wisch startet sofort den Scrub-Modus.

**Ursache:** `SiriRemoteScrubGesture` ist ein bildschirmfüllender, transparenter
`UIView` mit einem `UIPanGestureRecognizer` für indirekte (Siri-Remote-)Touches.
Er ist aktiv, sobald der Player nicht im Fehler-/Modal-Zustand ist — also auch,
während das Overlay mit den `Menu`-Buttons sichtbar ist. Auf tvOS ist genau
dieser Swipe das Signal, mit dem die Focus-Engine den Fokus auf die Buttons
bewegt. Der Pan-Recognizer schluckt ihn, daher:

- Der Fokus landet nie auf den Audio-/Untertitel-Buttons → unerreichbar.
- Jeder Swipe ruft sofort `beginScrub()` → Scrub-Modus.
- Ein Klick löst nur `onPlayPauseCommand` aus, nie ein Menü.

Die Buttons sind damit faktisch tote Controls.

## Lösung: zwei sich gegenseitig ausschließende Modi

Ein neuer Zustand trennt „Scrubben" sauber von „Controls bedienen". Beide Modi
können nie gleichzeitig aktiv sein, womit der Gesten-Konflikt entfällt.

### Transport-Modus (Standard)

Verhalten wie heute:
- Horizontales Wischen scrubbt (Trickplay-Vorschau).
- Klick = Play/Pause.
- ◀▶ (D-Pad) = ±10 s.

Visuell neu: **unten rechts**, unter der Wiedergabeleiste, zwei dezente
Icon-Buttons (Audio, Untertitel) mit dünner Amber-Outline. Sie sind in diesem
Modus reine Affordance — **nicht fokussierbar** —, damit der Scrub-Layer
weiterhin alle Swipes erhält. Keine erklärenden Texte, keine Status-Hinweise.

### Optionen-Modus

Auslöser: **nach unten** (D-Pad unten bzw. Klick unten am Trackpad) →
`onMoveCommand(.down)`.

Beim Eintritt:
- Der `SiriRemoteScrubGesture`-Layer wird aus der View-Hierarchie **entfernt**
  (Bedingung `controlMode == .transport` zusätzlich zu den bestehenden).
- Die Icon-Leiste wird `focusable()`, Fokus landet auf dem ersten Button.
- Wischen wechselt jetzt zwischen den Buttons (kein Scrubben).
- Klick auf ein Icon öffnet **über** der Leiste ein fokussierbares Track-Panel
  (eigenes Panel je Icon).
  - Audio-Panel: Liste der Audiospuren, aktive mit Häkchen.
  - Untertitel-Panel: „Aus", die Tracks, Trenner, „Online suchen …" (öffnet die
    bestehende Online-Suche).
  - Aktiver Track: amber-gefüllte Zeile mit Häkchen.

Verlassen: **Menu** oder **nach oben** → zurück in den Transport-Modus,
Scrub-Layer wird wieder eingehängt.

Play/Pause bleibt ausschließlich auf dem Klick — kein eigener Button.

## Visueller Stil

- Icons: dünne Amber-Outline (`Theme.accent`, ~55 % Deckkraft, 1 px Rand),
  transparenter Fill. Position: **unten rechts**, unter der Wiedergabeleiste.
- Fokus eines Buttons: amber gefüllt, dunkles Icon (`Theme.accentText`) —
  tvOS-Fokus-Konvention, kein wuchtiges Glow.
- SF-Symbols wie bisher (`speaker.wave.2`, `captions.bubble`/`.fill`).

## Technische Änderungen

### `PlayerViewModel`
- Neuer beobachteter Zustand `enum ControlMode { case transport, options }`,
  `var controlMode: ControlMode = .transport`.
- `enterOptions()` / `exitOptions()` (Letzteres schließt auch ein offenes Panel).
- Audio-/Untertitel-Auswahl nutzt weiter `selectAudioTrack` / `selectSubtitleTrack`
  und `presentSubtitleSearch` — unverändert.
- Beim Wechsel in `.options` Overlay sichtbar halten (Auto-Hide unterdrücken,
  analog zu `isScrubbing`); beim Verlassen Auto-Hide wieder zulassen.

### `SiriRemoteScrubGesture`
- Pan-Recognizer ignoriert vertikal-dominante Gesten, damit „nach unten" als
  `onMoveCommand(.down)` durchkommt. Umsetzung über
  `UIGestureRecognizerDelegate.gestureRecognizerShouldBegin` bzw. Auswertung der
  initialen Translation (`|dy| > |dx|` → nicht beginnen).

### `PlayerScreen`
- Scrub-Layer-Bedingung erweitern: zusätzlich `model.controlMode == .transport`.
- `onMoveCommand(.down)` im Transport-Modus → `model.enterOptions()`.
- `onExitCommand`: zuerst Optionen-Modus/Panel schließen, dann (wie bisher)
  Scrub abbrechen bzw. Player verlassen. Reihenfolge:
  Panel → Optionen-Modus → Scrub → dismiss.

### `PlayerOverlayView`
- `controlRow` von **über** dem Scrubber nach **unter** den Scrubber, rechts
  ausgerichtet, neuer Icon-Stil.
- Im Transport-Modus: nicht fokussierbare Icons.
- Im Optionen-Modus: fokussierbare Buttons + Track-Panel; bestehende `Menu`-
  Konstruktion entfällt.
- Mittlerer Status-Text in `normalFooter` (`◀▶ ±10 s …`) entfällt.

## Nicht im Scope

- Kapitel-Navigation.
- Wiedergabegeschwindigkeit.
- Änderungen an der Online-Untertitelsuche selbst (nur Aufruf-Pfad bleibt).

## Tests / Verifikation

Manuell auf dem Apple TV (Simulator deckt indirekte Touches nur teilweise ab):
1. Transport: Wischen scrubbt, Icons nicht fokussierbar, kein Status-Text.
2. Nach unten → Icons fokussierbar, Scrubben aus.
3. Untertitel-Icon → Panel, Track wählen wirkt, „Online suchen …" öffnet Suche.
4. Audio-Icon → Panel, Spurwechsel wirkt.
5. Menu/nach oben → zurück in Transport, Scrubben wieder aktiv.
