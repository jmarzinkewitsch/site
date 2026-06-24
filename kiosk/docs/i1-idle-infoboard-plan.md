# I1 — Idle-Infoboard („Bahnhofs-Screens") — Umsetzungsplan

> **Für Agenten:** Setze genau dein zugewiesenes Paket um. Halte dich **exakt** an
> den Daten-Vertrag und die Tafel-Schnittstelle unten. TDD wo Backend, volle Suite
> grün halten (`cd vault-api && .venv312/bin/python -m pytest -q`), Commit pro
> Paket, `git add` nur deine Dateien, **nicht** auf den NAS deployen.

**Ziel:** Der Leerlauf wird eine rotierende Bahnhofs-Anzeige: vollflächige
Einzeltafeln (Wetter, Film, Serie, Schlagzeile, Foto, Now Playing) in einem
durchgehenden Rahmen. Konzept + Designsprache: `kiosk/docs/idle-infoboard-concept.md`.

**Designentscheidungen (fix):**
- **Eine** Uhr pro Tafel, in der Rail, **im normalen Kiosk-Stil** (wie die Top-Bar-Uhr) — keine Split-Flap-Kachel-Uhr.
- **Split-Flap = nur Flip-Animation** beim Wechsel der **Gleis-Zeile/Tafel-Label** (und optional der Content-Headline). Die Uhr tickt normal.
- **Keine Nachttafel** (Display schläft via Präsenz, OS-seitig).
- **News:** `input_text.hamburg_news_headline` + `input_text.hamburg_news_summary`.
- **Fotos:** **Personenfilter** (`mode: people`, `person_ids`), vom Nutzer geliefert; Fallback Album/Random.

## Parallelisierung

- **A1, A2, C1** können **sofort parallel** laufen (disjunkte Dateien: A1=`homeassistant.py`, A2=`immich.py`/`config.py`, C1=Frontend-SPA).
- **A3** (Aggregations-Endpunkt) nutzt A1+A2 — kann gegen die hier definierten Signaturen **parallel** entwickelt und am Ende integriert werden.
- **C1 ist EIN Agent** (Single-File-SPA `web/kiosk/app.js` — nicht über mehrere Agenten splitten).

---

## Daten-Vertrag (A3 liefert, C1 konsumiert) — verbindlich

```
GET /kiosk/idle/overview        (require_bearer_or_kiosk)
{
  "weather":  { "temperature": number, "condition": string,
                "forecast": [ { "when": "18 Uhr"|"Mi", "condition": string, "temperature": number }, … ] } | null,
  "film":     { "id": string, "title": string, "subtitle": string, "reason": string|null,
                "backdrop_url": string, "type": "Movie" } | null,
  "series":   { "id": string, "title": string, "subtitle": string,
                "backdrop_url": string, "type": "Series" } | null,
  "headline": { "title": string, "summary": string } | null,
  "photos":   [ string, … ],          // bereits geproxyte URLs: /photos/image/{id}
  "now_playing": { "kind": "music"|"podcast", "title": string, "subtitle": string,
                   "image_url": string|null, "position": number|null, "duration": number|null } | null
}
```

Jedes Feld `null`/leer ⇒ die zugehörige Tafel fällt aus dem Zyklus. `backdrop_url`/
`image_url` sind **immer** vault-api-Proxy-URLs (kein fremder Host/Key).

## Tafel-Schnittstelle (C1-intern) — verbindlich

```js
// Jede Tafel ist ein Objekt in einer Registry:
{ id: "weather",
  label: "WETTER · HAMBURG",       // Gleis-Label (Flip beim Wechsel)
  dwellMs: 15000,                  // Verweildauer
  has(data) { return !!data.weather; },   // nur rotieren, wenn Inhalt da
  render(contentEl, data) { /* füllt die Inhaltszone */ } }
```

---

## Paket A1 — entfällt (kommt aus H1)

Der Wetter-Forecast-Helper wird **parallel in Paket H1** (Heute-Ausbau, Codex)
gebaut: `HomeAssistantService.weather_forecasts(entity_id, *, forecast_type="daily"|"hourly")`
→ Liste `[{ "datetime", "condition", "temperature", "templow"?, "precipitation_probability"? }, …]`.
**Nicht doppelt bauen.** A3 nutzt diese Methode (Signatur von H1). Falls H1 noch
nicht gemerged ist, wenn A3 startet: gegen diese Signatur entwickeln und beim
Integrieren abgleichen.

## Paket A2 — Immich-Personenfilter (Backend)

**Files:** Modify `vault-api/services/immich.py`, `vault-api/config.py`; Test `vault-api/tests/test_photos.py` (erweitern).

**Config:** `KioskPhotosConfig` erweitern um `mode: str = "random"` (`random|album|people`)
und `person_ids: list[str] = []`.

**Produces:** `ImmichService.people_assets(person_ids: list[str], *, count: int) -> list[PhotoItem]`
— Assets nach Personen über die Immich-Such-API: `POST /api/search/metadata`
mit Body `{ "personIds": person_ids, "size": count, "type": "IMAGE" }`; Response
`{"assets":{"items":[…]}}` → `_photo(...)` mappen. (Endpoint-Signatur **gegen die
laufende Immich-Instanz verifizieren** — Doku https://docs.immich.app/api/ ; bei
Abweichung dokumentieren und auf `album`/`random` zurückfallen.)

- [ ] `photos/overview` wählt nach `mode`: `people` → `people_assets(person_ids)`, sonst Album/Random (wie bisher), mit Fallback auf Random wenn leer.
- [ ] Test (Immich-HTTP gemockt): `mode=people` ruft `/api/search/metadata` mit `personIds`; mappt Assets auf `/photos/image/{id}`.
- [ ] Suite grün, Commit `feat(immich): people-based photo filter`.

## Paket A3 — `GET /kiosk/idle/overview` (Backend, nutzt A1/A2)

**Files:** Create `vault-api/routers/idle.py`; Modify `vault-api/main.py` (mount), `vault-api/models.py` (Modelle `IdleOverview`, `IdleWeather`, `IdleForecast`, `IdleMediaCard`, `IdleHeadline`, `IdleNowPlaying`); Test `vault-api/tests/test_idle.py` (neu).

**Logik (alles tolerant, `gather(return_exceptions=True)` je Quelle; eine kaputte Quelle ⇒ Feld `null`, nie 5xx):**
- `weather`: `config.kiosk_home.weather.entity_id` → State (jetzt) + `weather_forecast(...)` (A1) → kompakt auf `forecast[]` mappen (4 Einträge: nächste 2 Stunden + 2 Tage, „when" deutsch).
- `film`/`series`: aus `/kiosk/media/overview`-Quellen (`latest_movies` / `latest_series`) je **ein** Item; Serie **dedupe nach `series_id`** (max. 1). `backdrop_url` über den vorhandenen Proxy (`/kiosk/media/image/{id}?kind=backdrop`).
- `headline`: `hamburg_news_headline` (→ `title`) + `hamburg_news_summary` (→ `summary`).
- `photos`: `/photos/overview`-Logik (A2) → Liste von `/photos/image/{id}`-URLs.
- `now_playing`: aus `/music/zones` (spielende Zone) bzw. `/podcasts/nowplaying`; `null` wenn nichts läuft. `image_url` über den jeweiligen Proxy.

- [ ] Tests (Doubles): voll bestückt → alle Felder; einzelne Quelle wirft → Feld `null`, HTTP 200; Serie-Dedupe greift.
- [ ] `require_bearer_or_kiosk`; Suite grün, Commit `feat(kiosk): aggregated /kiosk/idle/overview`.

## Paket C1 — Idle-Board Frontend (EIN Agent)

**Files:** Modify `vault-api/web/kiosk/app.js`, `vault-api/web/kiosk/app.css`, `vault-api/web/kiosk/index.html`.

Baut auf dem vorhandenen Idle-Controller auf (`idleTimer`, `ambientRotationTimer`,
`IDLE_TIMEOUT_MS`, `ambientWakePage` in `app.js`).

**Aufgaben:**
1. **Board-Template (HTML/CSS):** vollflächiger Idle-Layer mit
   - **Rail** oben: Identität (◆ ZUHAUSE) · Datum · **Uhr im normalen Kiosk-Stil** (dieselbe Darstellung/Funktion wie die Top-Bar-Uhr — wiederverwenden, **keine** Split-Flap-Kacheln). **Genau eine** Uhr je Tafel.
   - **Inhaltszone** (vollflächig, Tafel-spezifisch; Text über Bild immer mit Scrim).
   - **Gleis-Zeile** unten: Tafel-Label · Takt-Punkte · „weiter in N s ›".
2. **Split-Flap-Flip** nur auf die **Gleis-Label**-Änderung (und optional Content-Headline) beim Tafelwechsel — kurze CSS-Flip-Animation. Inhalt sonst ruhig (Cross-Fade).
3. **Tafel-Registry** (Schnittstelle oben) mit den sechs Tafeln: `weather`, `photo`, `film`, `series`, `headline`, `nowplaying` — `render()` je Tafel nach Daten-Vertrag. Tafeln ohne Inhalt (`has()===false`) fallen raus.
4. **Daten:** beim Idle-Eintritt + alle ~5 min `GET /kiosk/idle/overview` laden; Tafeln rendern daraus (keine 5 Einzel-Polls).
5. **Rhythmus:** kuratierte Reihenfolge (Foto als Atempause zwischen Info-Tafeln), gewichtete `dwellMs`, **Tageszeit-Mix** (abends Film/Serie zuerst, tagsüber ausgewogen — einfache Gewichtung nach `new Date().getHours()`).
6. **Now-Playing-Pin:** läuft Musik/Podcast (`now_playing != null`), kommt die NowPlaying-Tafel häufiger/länger.
7. **Aufwecken:** Antippen beendet Idle sofort und kehrt zu `ambientWakePage` zurück (vorhandenes Verhalten beibehalten/erweitern).

**Akzeptanz:**
- Nach Inaktivität rotieren nur Tafeln **mit** Inhalt, vollflächig, je eine Botschaft.
- Eine Uhr, im normalen Kiosk-Stil; Label flippt beim Wechsel.
- Antippen weckt zur letzten Bedien-Seite.
- Kein Overlap/Überlauf im 1280×800-Viewport.

- [ ] Manuell + Headless-Screenshot prüfen; Commit `feat(kiosk): idle infoboard (Bahnhofs-Tafeln)`.

## Integrationsreihenfolge
1. **A1, A2, C1** parallel. **A3** parallel gegen den Vertrag, integriert nach A1/A2.
2. Danach (Mensch): `/kiosk/idle/overview` live prüfen, `person_ids` + `mode:people` in die Config, deployen.
3. Restliche Pakete aus `kiosk-screen-review-next.md` (M/V/H) bleiben unabhängig.
