# Vault — Architektur: API-First (Konzept)

Stand: Planungsdokument, noch kein Code. Ersetzt das frühere
„Requests & Empfehlungen"-Konzept und hebt es auf die Architektur-Ebene.

## Grundsatzentscheidung

Die tvOS-App kennt **genau einen Endpunkt: `vault-api`** auf dem NAS. Kein
direkter Call aus der App an Jellyfin, Radarr, Sonarr, TMDB, OMDb oder Claude.
Alle fremden Keys und Credentials liegen im Backend. Die App ist ein reiner
Client und kennt nur zwei Dinge: die **vault-api-URL** und einen
**Bearer-Token**.

**Einzige Ausnahme — der Videostream.** Die Stream-*Bytes* fließen direkt von
Jellyfin zur App. Die dafür nötige URL kommt von vault-api, die Daten nicht.
Das ist unkritisch, weil alles im selben LAN bzw. sogar auf demselben
Docker-Host läuft (Jellyfin, vault-api, Redis, Radarr/Sonarr, Roon).

## Annahmen & Scope

- **LAN-first.** Alle Dienste laufen lokal auf einem Gerät. Remote-Zugriff von
  unterwegs ist *kein* aktuelles Designziel. Falls später nötig, kommt Jellyfin
  hinter denselben Reverse-Proxy (SWAG/Authelia) wie vault-api — die App-Seite
  ändert sich dafür nicht.
- Der Jellyfin-`api_key` steckt damit zwangsläufig in der direkten Stream-URL
  (Jellyfin kann keine sauber signierten Kurz-URLs). Im reinen LAN-Betrieb ist
  das akzeptabel. vault-api gibt pro Abruf eine frische URL aus und cacht sie
  nicht.

## Warum API-First

- **Kein fremder API-Key liegt je auf dem Gerät.**
- **Logik ändern ohne tvOS-App-Update.** Besonders wertvoll, weil ein
  Sideload-Update (Xcode-Build, signieren, neu installieren) lästig ist — die
  oft iterierte Empfehlungslogik bleibt serverseitig.
- **Caching, Rate-Limiting, LLM-Kosten** einmal gebaut, gilt für tvOS, iPad,
  Browser und alles Spätere.
- **Neue Dienste** (Roon, weitere Metadatenquellen) → nur Backend ändern.
- **Dünner Client** → weitere Plattformen später mit minimalem Aufwand.

Ehrlicher Tradeoff: vault-api + Redis sitzen damit im **kritischen Pfad für
alles**, auch fürs Ansehen eines lokalen Films. Fällt das Backend aus, läuft
nichts — obwohl Jellyfin gesund ist. Deshalb: vault-api robust halten und, wo
möglich, bei Backend-Teilausfall sinnvoll degradieren.

## Konfiguration per Web-Oberfläche (zentrales Komfort-Feature)

Keys und Credentials am Apple TV einzutippen ist mühsam — deshalb **konfiguriert
man vault-api über eine kleine Web-Admin-UI im LAN**, nicht über die App.

Die Admin-UI bietet:

- Pro Dienst URL + Key/Token eintragen: Jellyfin, Radarr, Sonarr, TMDB, OMDb,
  Anthropic (Claude), optional Roon.
- **„Verbindung testen"** je Dienst (ruft intern dessen Health/Ping).
- **Vault-Bearer-Token** erzeugen/anzeigen — den gibt man **einmalig** am Apple
  TV ein (kurzer Code, später optional QR/Pairing).
- Standard-Auswahl für Radarr/Sonarr (Quality-Profile, Root-Folder).
- Persistenz in `.env`/Config-Datei bzw. kleiner DB. Secrets nie ins Git.

Ergebnis am Apple TV: nur **vault-api-URL + Bearer-Token** eingeben, fertig.

## vault-api — Verantwortlichkeiten

FastAPI-Backend auf dem NAS, das alle externen Dienste orchestriert und eine
saubere, vault-spezifische API nach außen gibt.

**Intern angesprochen:** Jellyfin (Library, UserData, Stream-URLs),
Radarr/Sonarr (Lookup, Add, Queue), TMDB (Recommendations, Discover, Credits,
Keywords), OMDb (IMDB/RT/Metacritic), Claude (LLM-Begründungen, ab M7),
optional Roon (später).

### Endpunkte nach außen

```
Library
  GET  /library/movies              gefiltert, paginiert, inkl. Jellyfin-UserData
  GET  /library/series
  GET  /library/item/{id}           Detail inkl. externer Scores (M5)
  GET  /library/continue            Weiterschauen-Queue
  POST /library/item/{id}/progress  Fortschritt → Jellyfin
  POST /library/item/{id}/rating    Bewertung → Jellyfin

Streaming
  GET  /stream/{id}                 liefert frische Jellyfin-Stream-URL (nur URL)

Discovery & Empfehlungen
  GET  /discover/movies             TMDB Discover, nach Geschmack gefiltert
  GET  /discover/series
  GET  /recommend                   personalisierte Liste mit Begründungen
  GET  /search?q=                   Jellyfin + Radarr/Sonarr-Lookup

Anfragen
  POST /request/movie               → Radarr add + search
  POST /request/series              → Sonarr add + search
  GET  /request/queue               kombinierte Radarr/Sonarr-Download-Queue

Betrieb & Konfiguration
  GET  /health                      Liveness + jeder Dienst einzeln gemeldet
  GET  /admin                       Web-Config-UI (LAN)
  GET/POST /admin/config            Credentials lesen/setzen (Web-UI dahinter)
```

## Datenfluss

**Metadaten:** App → vault-api → Jellyfin/Radarr/Sonarr/TMDB/OMDb → vault-api
führt zusammen, cacht, antwortet → App.

**Videostream:**
```
App → vault-api   GET /stream/{id}
App ← vault-api   { "url": "http://jellyfin.local/Videos/…?api_key=…" }
App → Jellyfin    direkter HTTP-Stream (Bytes, kein Umweg) — LAN
```

## Caching-Strategie (Redis)

| Daten | TTL | Grund |
|---|---|---|
| Jellyfin Library | 15 min | ändert sich selten |
| Jellyfin Item Detail | 1 h | stabil |
| TMDB Metadaten | 7 Tage | praktisch unveränderlich |
| OMDb Scores | 7 Tage | praktisch unveränderlich |
| TMDB Recommendations | 24 h | Rate-Limit schonen |
| Radarr/Sonarr Queue | 30 s | muss aktuell sein |
| LLM-Begründungen | 24 h | teuer, Ergebnis stabil |
| Stream-URLs | — | Jellyfin-Token ist zeitgebunden |

**Invalidierung:** Nach `POST …/progress` und `…/rating` den betroffenen
Item- und Continue-/Library-Cache verwerfen, sonst zeigt die App bis zu 15 min
veraltete Watched-/Rating-Stände.

## Keys & Secrets — alle im Backend

| Secret | Wo | In der App sichtbar? |
|---|---|---|
| Jellyfin Token | NAS (Web-UI) | Nein |
| Radarr API Key | NAS (Web-UI) | Nein |
| Sonarr API Key | NAS (Web-UI) | Nein |
| TMDB API Key | NAS (Web-UI) | Nein |
| OMDb API Key | NAS (Web-UI) | Nein |
| ANTHROPIC_API_KEY | NAS (Web-UI) | Nein |
| Vault Bearer Token | App + NAS | Ja (einmalig eingeben) |

## tvOS-App — Networking radikal vereinfacht

```
Vault/Networking/
  VaultClient.swift     einziger HTTP-Client; Bearer-Auth, base URL aus Settings
  Models/               reine Swift-Structs, decodieren vault-api-JSON
    LibraryItem.swift
    StreamInfo.swift
    RecommendationItem.swift
    RequestResult.swift
    QueueItem.swift
```

Kein `JellyfinService`, kein `RadarrService`, kein `TMDBService` in der App.

**Was vom bestehenden Swift-Code überlebt:** die Player-Engine
(`Vault/Player/*`), die gesamte UI, das Theme. **Was ersetzt wird:** der
Jellyfin-Networking-Layer → schlanker `VaultClient`. Der Player braucht
ohnehin nur „Stream-URL + Header"; die kommen künftig aus `/stream/{id}`.

## vault-api — Ordnerstruktur

```
vault-api/
  main.py                FastAPI-App, Router-Registrierung, Admin-UI mounten
  auth.py                Bearer-Token-Middleware
  cache.py               Redis-Wrapper, TTL- und Invalidierungs-Helpers
  config.py              Credentials laden/speichern (von der Web-UI gefüttert)
  routers/
    library.py  stream.py  discover.py  recommend.py  request.py  health.py
    admin.py             Web-Config-UI + /admin/config
  services/
    jellyfin.py  radarr.py  sonarr.py  tmdb.py  omdb.py  llm.py
    recommender.py       TasteProfile + Scoring (reine Logik, gut testbar)
  web/                   Admin-UI (Templates/Static oder kleines SPA)
  docker-compose.yml     vault-api + redis
  .env                   Secrets, nie ins Git
```

---

## Fachlich: Anfragen (Radarr/Sonarr)

Beide haben fast deckungsgleiche v3-APIs, Auth per `X-Api-Key`. Der
`lookup`-Endpunkt proxyt selbst TMDB/TVDB — fürs reine Anfragen braucht das
Backend daher **keinen eigenen TMDB-Key**, und die Antwort sagt, ob ein Titel
schon vorhanden ist.

| Zweck | Radarr | Sonarr |
|---|---|---|
| Suche/Lookup | `GET /api/v3/movie/lookup?term=` | `GET /api/v3/series/lookup?term=` |
| Quality-Profile | `GET /api/v3/qualityprofile` | `GET /api/v3/qualityprofile` |
| Root-Folder | `GET /api/v3/rootfolder` | `GET /api/v3/rootfolder` |
| Hinzufügen+suchen | `POST /api/v3/movie` | `POST /api/v3/series` |
| Download-Status | `GET /api/v3/queue` | `GET /api/v3/queue` |

Status-Logik kombiniert: nicht in Bibliothek & nicht in *arr* → **„Anfragen"**;
in *arr* ohne Datei → **„lädt"** (Fortschritt aus `/queue`); in Jellyfin →
**„Abspielen"**.

## Fachlich: Empfehlungen

- **Geschmackssignal:** Jellyfins eigene 0–10-Bewertung (schreibbar) plus
  implizite Signale (durchgeschaut/abgebrochen, Rewatches, Favoriten). Kein
  eigener Speicher nötig.
- **Externe Scores:** Jellyfin liefert teils `CommunityRating` (≈ IMDB) und
  `CriticRating` (≈ RT); für volle IMDB/RT/Metacritic kommt OMDb dazu (per
  IMDB-ID), TMDB liefert Genres/Keywords/Cast + Kandidaten.
- **Engine:** Für einen Einzelnutzer **content-based**, in `recommender.py`:
  Profil aus hoch bewerteten Titeln (Genres/Keywords/Regie/Cast/Jahrzehnt
  gewichtet) → Kandidaten aus TMDB `recommendations`/`discover` → Scoring
  (Ähnlichkeit × Profil, plus Qualitäts-Score, plus Neuheitsbonus) mit
  Klartext-Begründung.
- **Optional LLM (M7):** Claude rankt/begründet die Top-Kandidaten natürlicher.
  Serverseitig, gegen echte TMDB-Titel geerdet.

**Die Schleife:** Empfehlungen enthalten oft Titel außerhalb der Bibliothek →
jede bekommt je nach Status „Abspielen" oder „Anfragen". Entdecken → anfragen →
herunterladen → ansehen.

---

## Milestone-Zuordnung

**Voraussetzung:** Der Custom-Player muss auf echtem Apple TV bauen und ein MKV
abspielen. Das ist das größte ungeprüfte Risiko — kein zweites unerprobtes
System davor stapeln, bevor der Player lief. Der Player zeigt dafür einfach auf
`/stream/{id}`.

- **M1–M3 — Kern:** vault-api baut `/health`, `/library/*`, `/stream/*` **und
  die Web-Config-UI**. tvOS-App: nur `VaultClient`, keine externen Calls.
- **M4 — Anfragen:** `/request/*`, `/search`; Radarr/Sonarr-Logik im Backend.
- **M5 — Bewertungen & Scores:** OMDb in `/library/item/{id}`,
  `POST …/rating` schreibt an Jellyfin.
- **M6 — Empfehlungen:** `/recommend`, `recommender.py`, TMDB Discover. Kein
  App-Update für neue Empfehlungslogik nötig.
- **M7 — LLM:** Claude in `recommender.py`; die App merkt nichts, `/recommend`
  liefert nur bessere Begründungen.
- **Später (optional):** Roon-Integration — durch API-First nur eine
  Backend-Erweiterung.

## Was zuerst gebaut wird (während kein Mac da ist)

vault-api ist **Python und damit sofort baubar und testbar**, auch ohne Apple
TV. Reihenfolge: Projektgerüst (FastAPI + Redis + Docker) → `config.py` +
Web-Config-UI → `services/jellyfin.py` → `/health`, `/library/*`, `/stream/*`.
Die tvOS-Anbindung (`VaultClient` + Player auf `/stream`) folgt am Mac.

## Offene Entscheidungen

1. Discovery über *arr*-`lookup` (kein TMDB-Key) oder direkt TMDB? — Tendenz:
   `lookup` zuerst, TMDB für Empfehlungen.
2. OMDb-Key holen, oder reichen Jellyfins vorhandene Rating-Felder?
3. LLM-Begründungen ja/nein (Kosten vs. Erlebnis)?
4. Sollen Empfehlungen auch vorhandene Bibliotheks-Titel mischen oder bewusst
   auf neue, anfragbare fokussieren?
5. Roon: nur Statusanzeige, oder Steuerung — und in welchem Milestone?
