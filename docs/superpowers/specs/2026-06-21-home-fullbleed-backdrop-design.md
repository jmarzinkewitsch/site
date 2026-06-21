# Home: Vollbild-Backdrop hinter dem ganzen Screen (tvOS)

**Datum:** 2026-06-21
**Status:** Design, freigegeben — Umsetzung folgt

## Problem

Auf dem Home-Screen steckt der Backdrop in der `StageView`, ist auf
`Theme.stageHeight` (620 pt) begrenzt und wird beim Scrollen ausgeblendet. Die
Shelves landen dann auf einfarbigem `Theme.bg`, und der obere Bildrand wirkt
unter der tvOS-Menüleiste angeschnitten.

## Ziel

Der Backdrop wird zu einer **Vollbild-Ebene hinter dem kompletten Screen** —
hinter Stage, Shelves und (durch das native Bar-Material durchscheinend) der
Menüleiste. Er bleibt beim Scrollen stehen und **blendet zum Backdrop des
fokussierten Items über**. Ein Scrim dunkelt nach unten und beim Scrollen ab,
damit Texte und Shelves lesbar bleiben.

**Unverändert:** Menüleiste (native `TabView`-Bar + `TopBar`-Clock) und das
Stage-Layout (Kicker, Logo, Meta, Overview, Fortschritt), inklusive Ausblenden
der Stage-Texte beim Scrollen, damit sie nicht mit den Shelves kollidieren.

## Umsetzung

### `StageView` aufteilen
Backdrop und Info-Spalte entkoppeln:

- **`BackdropView`** (neu) — full-bleed Hintergrund:
  - `RemoteImage` füllt den **ganzen Screen** (`ignoresSafeArea()`), nicht mehr
    nur `stageHeight`. Crossfade bei Wechsel von `item.id` (wie heute).
  - Ambient-Glow (dominante Bildfarbe) wie bisher.
  - Lesbarkeits-Scrims:
    - vertikal: oben leicht abgedunkelt (hinter der Bar) → Mitte klar → unten
      `Theme.bg` (für die Shelves),
    - horizontal von links (für die Stage-Texte), wie heute.
  - **Scroll-Abdunklung:** zusätzlicher `Theme.bg`-Overlay, dessen Deckkraft mit
    `scrollY` steigt (`min(maxScrim, scrollY / fadeDistance)`, gedeckelt ~0.7).
    Das Bild bleibt sichtbar, tritt aber zurück.
- **`StageInfoView`** (= heutiges `info(for:)`) — Kicker/Logo/Meta/Overview/
  Fortschritt, unverändert.

### `HomeView`
ZStack-Reihenfolge (unten → oben):
1. `Theme.bg` (Fallback).
2. `BackdropView(item: currentStageItem, imageURL:, scrollY:)` — full screen,
   bleibt stehen (kein `stageOpacity` mehr auf dem Bild).
3. `StageInfoView(item: currentStageItem)` — oben links positioniert wie heute,
   weiterhin mit `.opacity(stageOpacity)` (fadet beim Scrollen aus).
4. `ScrollView` mit den Shelves; Hintergrund **transparent**, damit der Backdrop
   durchscheint. Top-Spacer `Color.clear.frame(height: stageHeight)` bleibt.

`stageOpacity` (Fade über `stageFadeDistance`) gilt künftig **nur** für die
Stage-Info, nicht mehr für den Backdrop.

## Nicht im Scope

- Änderungen an Menüleiste / `TopBar`.
- Neues Stage-Layout oder neue Metadaten.
- Detail-/andere Screens.

## Verifikation

Manuell in der App mit echten Backdrops:
1. Backdrop füllt den ganzen Screen, auch hinter den Shelves.
2. Fokuswechsel in den Shelves blendet den Backdrop über.
3. Scrollen: Bild bleibt, dunkelt ab; Shelves bleiben lesbar; Stage-Texte faden
   aus.
4. Menüleiste und Stage-Inhalte sehen aus wie zuvor.
