# Idle-Infoboard — „Bahnhofs-Screens" (Konzept)

Stand: 2026-06-24. Konzept für Paket **I1**. Ersetzt den heutigen
Ambient-/Foto-Slideshow-Modus durch einen ruhigen, rotierenden **Infotafel-
Modus** im Stil einer Bahnhofs-Anzeige. Kein Implementierungs-Ticket — das ist
das Zielbild + die Designsprache, aus der dann Tasks geschnitten werden.

## 1. Leitidee

Eine Bahnhofs-/Flughafentafel funktioniert, weil sie **eine** Sache groß und
ruhig zeigt und in einem **vorhersehbaren Takt** wechselt. Man erfasst sie in
zwei Sekunden quer durch den Raum. Genau das soll der Kiosk im Leerlauf werden:
**nicht** ein Dashboard mit zehn Kacheln, sondern eine Folge **einzelner,
vollflächiger Tafeln** mit je einer starken Botschaft.

Drei Prinzipien:

1. **Eine Botschaft pro Tafel.** Wetter *oder* ein Film *oder* eine Schlagzeile —
   nie gemischt. Große Typo, viel Luft, aus 3 m lesbar.
2. **Ein durchgehender Rahmen.** Alle Tafeln teilen sich dasselbe Gerüst (Stations-
   uhr oben, Inhaltszone, „Gleis"-Zeile unten). Die Konsistenz macht aus einer
   Diashow eine *Anzeigetafel*.
3. **Ruhiger, kuratierter Takt.** Feste, gewichtete Verweildauern und eine
   *kuratierte Reihenfolge* — kein Zufalls-Geflacker.

## 2. Das Tafel-Template (der durchgehende Rahmen)

Jede Tafel rendert in dieselbe dreigeteilte Struktur — das ist der Kern der
Bahnhofs-Anmutung:

```
┌──────────────────────────────────────────────────────────┐
│  ◆ ZUHAUSE            Di · 24. Juni            21:47       │  ← Stations-Rail
│                                                            │     (immer da)
│                                                            │
│              ⟨  vollflächige Inhaltszone  ⟩                │  ← eine Botschaft
│                                                            │
│                                                            │
│  WETTER · HAMBURG                          ●○○○○  ›        │  ← „Gleis"-Zeile
└──────────────────────────────────────────────────────────┘     (Kontext + Takt)
```

- **Stations-Rail (oben, schmal, immer gleich):** Identität (◆ ZUHAUSE), Datum,
  **große Uhr** als Anker — wie die Bahnhofsuhr. Bleibt über alle Tafeln stehen.
- **Inhaltszone:** die eine große Botschaft. Bei Bild/Backdrop liegt ein
  Lesbarkeits-Scrim drunter, Text immer im unteren Drittel.
- **Gleis-Zeile (unten):** links ein **Tafel-Label** (WETTER · HAMBURG / FILM /
  SCHLAGZEILE …), rechts der **Rotations-Indikator** (Punkte zeigen, wo im Zyklus
  man ist) — wie „Gleis 4 · in 3 min". Gibt dem Wechsel Rhythmus und Erwartbarkeit.

## 3. Die Tafeln (Rotationsset)

| Tafel | Inhalt | Quelle | Verweildauer | Fallback |
|---|---|---|---|---|
| **Wetter** | jetzt + Verlauf heute + nächste Tage, groß | HA `weather.forecast_home` (Forecast via `weather.get_forecasts`) | ~15 s | überspringen |
| **Film** | eine Empfehlung, großer Backdrop, Titel, kurzer Grund | `/kiosk/media/overview` (latest_movies/spotlight) | ~18 s | überspringen |
| **Serie** | eine Empfehlung (max. eine Folge je Serie) | `/kiosk/media/overview` (latest_series, dedupe) | ~18 s | überspringen |
| **Schlagzeile** | **eine** Headline + 1–2 Sätze (eine Tafel je Story, Top ~5) | NDR-Hamburg-RSS (in vault-api) | ~14 s | überspringen |
| **Foto** | vollflächiges Immich-Bild, dezent Uhr | `/photos/overview` (Album „Kiosk", später Personenfilter) | ~28 s | überspringen |
| **Now Playing** | großes Cover, Titel/Interpret, dezenter Fortschritt | `/music/zones` bzw. `/podcasts/nowplaying` | gepinnt (s. u.) | nur wenn aktiv |

**Wichtig — nur Tafeln mit Inhalt rotieren.** Kein Wetter / kein Foto / keine
News → die Tafel fällt einfach aus dem Zyklus. Nie eine leere/kaputte Tafel.

## 4. Rhythmus, Kuration, Tageszeit

- **Kuratierte Reihenfolge statt Zufall.** Ein fester Zyklus wirkt wie ein
  Fahrplan, nicht wie ein Bildschirmschoner. Vorschlag:
  `Wetter → Foto → Film → Schlagzeile → Foto → Serie → Foto → …`
  (Foto als ruhiger „Atemzug" zwischen den Info-Tafeln).
- **Gewichtete Verweildauer** (oben in der Tabelle) — Foto darf lange stehen,
  Schlagzeile kurz.
- **Tageszeit-Mix (der Opus-Twist):** Die Tafel passt ihren Inhalt der Uhrzeit an,
  wie eine Station unterschiedliche Dinge zu unterschiedlichen Zeiten zeigt:
  - **Morgens** (6–11): Wetter + Termine-heute zuerst, Film/Serie selten.
  - **Tagsüber** (11–18): ausgewogen, Foto häufiger.
  - **Abends** (18–24): Film/Serie zuerst (Lean-back-Auswahl), Wetter selten.
  - **Nacht** (0–6): **„Nachttafel"** — nur abgedunkelte Uhr + ggf. ein dunkles
    Foto, keine grellen Backdrops.

## 5. Der Übergang — die Signatur

Der Wechsel zwischen Tafeln trägt die ganze Bahnhofs-Identität. Zwei Optionen:

- **A — Split-Flap (Solari).** Die klassische Fallblatt-Animation beim Tafel- bzw.
  Textwechsel. Maximaler Wiedererkennungswert, *ist* der Bahnhof. Risiko:
  kann gimmickig/teuer wirken, wenn überall.
  → **Empfehlung:** Split-Flap **gezielt** auf die **Stations-Rail** (Uhr/Datum)
  und die **Gleis-Zeile** (Tafel-Label), die große Inhaltszone wechselt per
  ruhigem Cross-Fade/Slide. So gibt es den Flip-Moment als Akzent, ohne dass das
  Foto „flattert".
- **B — durchgehend ruhig.** Nur Cross-Fade + die persistente Uhr. Eleganter/
  zurückhaltender, aber weniger „Bahnhof".

Ich empfehle **A in der dosierten Form** — ein Flip-Akzent als Erkennungszeichen,
Inhalt ruhig.

## 6. Aufwach-Verhalten

- **Antippen weckt sofort** und kehrt zur **vorher aktiven Bedien-Seite** zurück
  (`ambientWakePage` ist schon da). Das Board „parkt" die UI, Touch holt sie zurück.
- **Eintritt:** nach `IDLE_TIMEOUT_MS` (heute 60 s) ohne Berührung.
- **Media-Pin:** Läuft Musik/Podcast, ist **Now Playing die dominante Tafel** —
  sie kommt häufiger und länger, die anderen rotieren dezent dazwischen. (Im
  Leerlauf *ohne* Wiedergabe fällt sie raus.)

## 7. Technik (schlank, baut auf Vorhandenem auf)

- Der Idle-Controller existiert bereits (`idleTimer`, `ambientRotationTimer`,
  `AMBIENT_ROTATION_MS` in `web/kiosk/app.js`). I1 erweitert ihn um ein
  **Tafel-Modell**: `{ type, label, dwellMs, hasContent(), render(el) }` plus den
  kuratierten Zyklus und das Tafel-Template (CSS).
- **Datenbeschaffung gebündeln:** statt im Leerlauf 5 Endpunkte zu pollen, ein
  **aggregierter `GET /kiosk/idle/overview`**, der in *einem* Call liefert:
  Wetter(+Forecast), je eine Film-/Serien-Empfehlung (dedupe), Schlagzeile(n),
  Foto-Referenzen, Now-Playing-Status. Wird z. B. alle 5 min serverseitig
  aufgefrischt → der Kiosk rotiert nur durch fertige Daten, kein Geruckel.
- **Kein neuer fremder Key/Host am Client** — Fotos/Backdrops laufen über die
  bestehenden Proxys (`/photos/image`, `/kiosk/media/image`).
- **Wetter-Forecast** ist der einzige echte Backend-Zusatz: HA liefert den
  Forecast nicht mehr als Attribut, sondern über den Service `weather.get_forecasts`
  → in `services/homeassistant.py` ergänzen (deckt sich mit Paket **H1**).

## 8. Entscheidungen (getroffen 2026-06-24)

1. **Übergang:** Split-Flap **nur als Flip-Animation** beim Wechsel der
   **Gleis-Zeile/Tafel-Label** (und optional Content-Headline). Die **Uhr bleibt
   im normalen Kiosk-Stil** (wie die Top-Bar-Uhr), **eine** Uhr pro Tafel. Keine
   Split-Flap-Kachel-Uhr.
2. **News:** **NDR-Hamburg-RSS** direkt in vault-api (Top ~5 echte Schlagzeilen
   mit passender Summary) → eine Headline-Tafel pro Story. Die zwei
   `input_text.hamburg_news_*`-Entitäten fallen raus (mismatchte 100-Zeichen-
   Einzeiler; HAs Feedreader-Event liefert nur die jeweils neueste Story).
3. **Fotos:** **direkt Personenfilter** (`mode: people`, `person_ids` vom Nutzer),
   Fallback Album/Random.
4. **Nachttafel:** entfällt — das Display ist via Präsenz aus, wenn niemand da ist.
5. **Aggregations-Endpunkt `/kiosk/idle/overview`** wird gebaut.

Umsetzung in Paketen: `kiosk/docs/i1-idle-infoboard-plan.md`.
