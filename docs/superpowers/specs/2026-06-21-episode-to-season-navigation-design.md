# Folge öffnen → Staffel-Navigation mit markierter Folge

**Datum:** 2026-06-21
**Status:** Design, freigegeben — Umsetzung folgt

## Problem

Öffnet man vom Homescreen eine einzelne Folge, landet man auf deren Detail
(`ItemDetailView(summary: episode)`) ohne jede Möglichkeit, zu den anderen
Folgen der Staffel zu navigieren. Die Staffel-/Episodenliste (`seriesSection`)
existiert, wird aber nur bei `summary.kind == .series` gezeigt.

## Ziel

Beim Öffnen einer Folge: die Folge bleibt oben als Hero, **darunter** die
Staffel-Sektion (Staffel-Picker + Episodenliste) mit der **richtigen Staffel
vorausgewählt** und der **geöffneten Folge hervorgehoben**. Landefokus liegt
zuerst auf Play/Fortsetzen im Hero; der erste Druck nach unten springt direkt
auf die markierte Folge, die dabei in den sichtbaren Bereich scrollt.

## Umsetzung

### `DetailViewModel`
- Helper `seriesId(for:)`: `summary.kind == .series ? summary.id : summary.seriesId`.
- `load(summary:)`: für `.episode` zusätzlich `seasons(seriesId)` laden und die
  **Staffel der Folge** (`summary.seasonId`, Fallback erste Staffel) per
  `selectSeason` vorauswählen. `detail` bleibt die Folge (Hero unverändert).
- `refreshPlaybackState`: Episoden-Reload für `.episode` analog über
  `seriesId(for:)` statt `summary.id`.

### `ItemDetailView`
- `seriesSection` auch bei `.episode` rendern (unter dem Hero).
- In `seriesSection` die `seriesId` aus einem berechneten Wert nehmen
  (`summary.kind == .series ? summary.id : summary.seriesId ?? summary.id`),
  nicht mehr direkt `summary.id`.
- `highlightedEpisodeID = (summary.kind == .episode) ? summary.id : nil`.
- Fokus: `@Namespace`-Scope um die Episodenliste (`.focusScope`); die markierte
  Zeile bekommt `.prefersDefaultFocus(true, in: scope)`, sodass „nach unten" aus
  dem Hero direkt dort landet. Die Liste steht im äußeren `ScrollView` → der
  Fokus scrollt die Zeile automatisch in den sichtbaren Bereich. Initialer
  Screen-Fokus bleibt beim Hero-Play-Button (erstes fokussierbares Element).

### `EpisodeRow`
- Neuer Parameter `isHighlighted: Bool = false`. Wenn gesetzt: Amber-Rahmen
  (bzw. dezenter Amber-Hintergrund) um die Zeile, damit „deine" Folge sofort
  erkennbar ist.

## Verhalten unverändert

- Serie regulär öffnen (`.series`): wie bisher (erste Staffel, kein Highlight).
- Film/Trailer: unberührt.

## Nicht im Scope

- Staffelübergreifende „nächste Folge"-Logik (gibt es im Player bereits).
- Neues Episoden-Layout / horizontale Rail.

## Verifikation

In der App mit echten Serien:
1. Folge vom Home öffnen → Hero der Folge oben, darunter die Staffel mit der
   Folge hervorgehoben; richtige Staffel vorausgewählt.
2. Fokus startet auf Play; ein Druck nach unten landet auf der markierten Folge
   und scrollt sie ins Bild.
3. Andere Folgen/Staffeln lassen sich normal anwählen und abspielen.
4. Serie direkt öffnen verhält sich wie zuvor.
