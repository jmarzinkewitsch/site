# K4 Podcasts — Review-Nacharbeiten (für Codex)

Aus dem Code-Review der bestehenden K4/K6-Implementierung. **Keine Bugs** — der
Kern (Feed-Parser, resiliente Aggregation, Wiedergabe via Music Assistant,
Immich-Foto-Proxy) ist sauber und 242 Tests sind grün. Es fehlen vier
Plan-Funktionen plus zwei Kleinigkeiten. Jeweils mit Datei-Pointern und
Akzeptanzkriterium. Bitte TDD, volle Suite grün halten (`.venv312/bin/python -m
pytest -q`), Commit pro Punkt, **nicht** auf den NAS deployen.

Referenz fürs Design: `kiosk/docs/architecture.md` → Abschnitt „Podcasts (K4) — geklärt".

---

## 1. Resume- + „gehört"-Speicher (persistiert)

**Problem:** Aktuell gibt es nur die Live-Position aus HA (`/podcasts/nowplaying`).
Nichts wird gespeichert → kein Resume über Sessions, kein „erledigt".

**Plan:** „Resume + gehört-Status: ja, in vault-api (eigener SQLite-Speicher wie
die Rating-Snapshots) — pro Episode Position merken und ‚erledigt' markieren."

**Vorgehen:**
- Neues `services/podcast_store.py` analog zu `services/rating_store.py` (gleiches
  SQLite-Muster, `VAULT_DB_PATH`). Speichert pro `episode_id`:
  `position_seconds: float`, `completed: bool`, `updated_at`.
- Endpunkte in `routers/podcasts.py`:
  - `POST /podcasts/progress` Body `{ episode_id, position_seconds, completed }` → upsert.
  - Resume-Position in `PodcastEpisode`/`PodcastOverview` mitliefern (Feld
    `resume_seconds: float | None`, `completed: bool`), aus dem Store gemerged.
- Beim `/podcasts/play` optional an der gespeicherten Position fortsetzen
  (HA `media_player.media_seek` nach dem `play_media`, falls `resume_seconds`).

**Akzeptanz:** Test: progress speichern → `/overview` bzw. `/feed/.../episodes`
liefert `resume_seconds`/`completed`; erneutes Abspielen seekt an die Position.

## 2. Transport: ±30 s + Tempo

**Problem:** `services/homeassistant.py::media_player_transport` kann nur
play/pause/stop/next/previous. Der Plan will **±30 s-Skip** und **Tempo**.

**Vorgehen:**
- `/podcasts/transport` um eine Aktion `seek_relative` mit `{ seconds: ±30 }`
  erweitern: aktuelle `media_position` aus HA lesen, `media_player.media_seek`
  mit `seek_position = max(0, position + seconds)` aufrufen.
- Tempo „wo der Player es kann": Music Assistant kann das teils über einen
  eigenen Service — **best effort**: wenn der Ziel-Player das unterstützt,
  setzen, sonst ignorieren (kein harter Fehler). Sauber dokumentieren.

**Akzeptanz:** Test: `seek_relative {seconds:-30}` ruft `media_player.media_seek`
mit korrekt berechneter Absolutposition.

## 3. Discovery/Suche zum Abonnieren

**Problem:** Feeds kommen nur aus der Config (`kiosk_podcasts.feeds`). Es fehlt
das Finden/Abonnieren.

**Plan:** „Suche dient v. a. dem Hinzufügen" über einen Podcast-Index.

**Vorgehen:**
- `GET /podcasts/search?q=` über die **iTunes-Search-API** (keyless):
  `https://itunes.apple.com/search?media=podcast&term=<q>` → Liste
  `{ title, feed_url, image_url, author }`.
- `POST /podcasts/subscribe` Body `{ feed_url, title? }` → Feed in
  `kiosk_podcasts.feeds` aufnehmen und **persistieren** (über den ConfigStore,
  wie andere Config-Mutationen). `id` deterministisch aus der URL ableiten.
- OPML-Import (Apple-Abos) ist optional/später.

**Akzeptanz:** Test (iTunes-HTTP gemockt): Suche liefert Kandidaten; subscribe
fügt einen Feed hinzu, der danach in `/overview` auftaucht.

## 4. Roon im Zielraum pausieren beim Podcast-Start

**Problem:** Roon und Music Assistant koordinieren nicht — startet man einen
Podcast, läuft Roon im selben Raum evtl. weiter.

**Plan:** „beim Podcast-Start wird Roon im Ziel-Raum pausiert."

**Vorgehen:**
- `KioskPodcastPlayerConfig` um ein optionales `roon_zone_id: str = ""` erweitern
  (Mapping Podcast-Player → Roon-Zone).
- In `/podcasts/play` vor/nach `play_media`: wenn `roon_zone_id` gesetzt, Roon
  dort pausieren — über den bestehenden `RoonService`
  (`POST` an die Jukebox `transport {zoneId, action:"pause"}`, vgl.
  `routers/music.py`).

**Akzeptanz:** Test: bei gesetztem `roon_zone_id` wird der Roon-Transport mit
`pause` für die Zone aufgerufen.

---

## Kleinkram
- `routers/photos.py::image`: `Cache-Control: public, max-age=86400` setzen
  (konsistent mit dem Jellyfin-Image-Proxy in `routers/kiosk.py`).
- `routers/podcasts.py::play` holt zum Finden der Episode die ganze Overview neu
  — ok (gecacht), aber ein direkter `/feed/{id}/episodes`-Lookup wäre schlanker.
