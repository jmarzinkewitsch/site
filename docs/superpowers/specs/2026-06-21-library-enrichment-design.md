# Mediathek-Anreicherung: passende neue Filme → Radarr (hybrid)

**Datum:** 2026-06-21
**Status:** Design, freigegeben — Umsetzung folgt

## Ziel

Die Mediathek halb-/automatisch um Filme erweitern, die zu Jannos Profil passen.
Hybrid: stark passende Treffer werden **automatisch zu Radarr hinzugefügt**, der
Rest landet in einer **Review-Queue** in der App, die man per Klick
bestätigt/verwirft. Geplanter Lauf (NAS-Cron, wöchentlich) plus manueller Trigger.

## Entscheidungen (gewählt)

- **Automatik:** Hybrid (Auto-Add + Queue).
- **Kandidatenquelle:** TMDB `discover_movies_by_genres` nach Jannos Lieblings-
  genres (Popularität/Rating), kein strikter Aktualitäts-Filter. (Leichter
  Recency-Bias später optional.)
- **Profil:** vorerst nur **Janno** (`favorite_genres` + `fear_comfort`).
  Janno steht auf `fear_comfort=10` → **keine Fear-Grenze**; Auto-Add wird rein
  über Qualität + Genre-Match entschieden.
- **Auslöser:** geplant (NAS-Cron) **und** manuell (Button in der App).
- **Queue-Ort:** tvOS-App.

## Integration mit den bestehenden „Vorschlägen"

Zwei verschiedene Absichten, die sich ergänzen statt zu konkurrieren:

- **Picker (Vorschlag-Tab):** „Was schauen wir JETZT?" — Watch-Tonight, ein
  Bibliotheks-Pick + ein Discover-Pick. **Bleibt unverändert.**
- **Anreicherung:** „Mediathek wachsen lassen" — persistente Queue + Auto-Add.

Wiederverwendet wird so viel wie möglich:
- **Scoring-Kern:** `_discover_score`, `_discover_profile_score`,
  `_estimated_discover_fear` aus `recommender.py` — kein doppeltes Scoring.
- **Radarr-Add:** bestehender `RadarrService.add` / `RequestDetailView` /
  `POST /request/movie`.
- **UI:** der heute **nicht verdrahtete** `ForYouView` („Für dich neu"-Regal +
  `RequestDetailView`) wird wiederbelebt als Queue-Oberfläche.

## Backend (vault-api)

### Service `enricher.py`
Pipeline `run_enrichment(person="janno")`:
1. **Kandidaten:** `tmdb.discover_movies_by_genres(genre_ids(janno), pages=…)`.
2. **Entdoppeln:** raus, was schon in Jellyfin (per `tmdb_id`), schon in Radarr
   (`existing_by_tmdb`) oder schon im Store als `added/auto_added/dismissed` ist.
3. **Scoren** gegen Jannos Profil (Recommender-Scorer; Fear für Janno = 0-Effekt).
4. **Einsortieren** per Schwellwerten:
   - **auto_add:** Score ≥ `AUTO` **und** `vote_count ≥ MIN_VOTES` **und**
     `vote_average ≥ MIN_RATING` → `RadarrService.add`, Status `auto_added`,
     gedeckelt auf `MAX_AUTO_PER_RUN`.
   - **pending:** Score ∈ [`QUEUE`, `AUTO`) → in der Queue.
   - **verwerfen:** Rest.
5. Lauf-Zusammenfassung zurückgeben (auto-added N, queued M, geprüft K).

Startwerte (konfigurierbar): `AUTO=0.7`, `QUEUE=0.5`, `MIN_VOTES=150`,
`MIN_RATING=6.5`, `MAX_AUTO_PER_RUN=5`, `pages=3`.

### Persistenz `enrichment_store.py` (SQLite, wie `profile_store`)
Tabelle `enrichment_suggestions`: `tmdb_id` (PK), `person`, `title`, `year`,
`poster_url`, `score`, `reason`, `est_fear`, `status`
(`pending`/`auto_added`/`added`/`dismissed`), `created_at`, `decided_at`.
Merkt sich entschiedene/hinzugefügte Titel, damit nichts doppelt vorgeschlagen
oder erneut hinzugefügt wird.

### Endpoints `routers/enrich.py` (bearer-auth)
- `POST /enrich/run` → Pipeline jetzt; liefert Zusammenfassung.
- `GET  /enrich/suggestions` → `pending` (+ optional zuletzt `auto_added` zur Info).
- `POST /enrich/suggestions/{tmdb_id}/accept` → `RadarrService.add`, Status `added`.
- `POST /enrich/suggestions/{tmdb_id}/dismiss` → Status `dismissed`.

### Config (admin)
Schwellwerte + aktive Person im Config-Store (nutzt vorhandene
`radarr_defaults` für Quality-Profil/Root-Folder beim Add).

## Scheduling
NAS-Cron ruft wöchentlich `POST /enrich/run` (bearer). Entkoppelt, in den Logs
sichtbar. Der App-Button trifft denselben Endpoint.

## tvOS-App — gemeinsamer Vorschlag-Tab

Ein Tab, ein vertikaler Scroll, zwei Zonen (Reihenfolge: Neues zuerst):

1. **„Neu für dich" (Enrichment-Queue) — oben.**
   - Horizontales Poster-Regal aus `GET /enrich/suggestions` (`pending`).
   - Kopfzeile: Titel „Neu für dich", **Anzahl-Badge** (`N neu`), Info-Chip
     „M automatisch ergänzt", rechts **„Jetzt suchen"** (`POST /enrich/run`,
     danach Liste neu laden).
   - Pro Karte: Poster, Titel/Jahr, kurze Begründung (`reason`), amber **„+"**.
     Fokus = Amber-Ring.
   - **Interaktion:** Klick = `RequestDetailView` (Details + Hinzufügen →
     `accept` → Radarr); **Menü-Taste = Verwerfen** (`dismiss`, via
     `.contextMenu`/`onExitCommand`-Pattern wie sonst).
   - **Leere Queue:** Sektion blendet sich aus, nur eine schmale
     „Jetzt suchen"-Zeile bleibt, damit der Picker primär ist.
   - Umsetzung: den heute **nicht verdrahteten `ForYouView`** als Basis für dieses
     Regal wiederverwenden, gespeist aus dem Enrichment-Store statt aus den
     ephemeren Recommend-Discover-Items.

2. **Trennlinie.**

3. **„Was schauen wir?" (Picker) — unten, unverändert.** Der bestehende
   `PickerSelectionView`-Inhalt (Persona · Stimmung · Genre · Länge · „Vorschlag
   holen" → `PickerResultsView`) wandert unter die Queue in denselben Scroll.

Mockup: siehe Widget `vault_vorschlag_combined_tab_design` in der Session vom
2026-06-21 (Queue-Regal oben mit „+"-Badges und „Jetzt suchen", Picker darunter).

## Nicht im Scope (später)
- Tanno / „beide" inkl. vorsichtiger Fear-Grenze (Design steht, aktiviert sich
  über die Profil-Basis).
- Serien-Anreicherung (Sonarr).
- Strikter Aktualitäts-/Verfügbarkeits-Filter (Region/Sprache).

## Verifikation
1. `POST /enrich/run`: Kandidaten kommen, Dedup greift (nichts aus Bibliothek/
   Radarr), Auto-Adds erscheinen in Radarr, Queue füllt sich.
2. App: Queue zeigt `pending`, Hinzufügen landet in Radarr + verschwindet aus der
   Queue, Verwerfen entfernt dauerhaft (kommt nicht wieder).
3. Zweiter Lauf schlägt nichts doppelt vor.
4. Picker („Was schauen wir?") unverändert.
