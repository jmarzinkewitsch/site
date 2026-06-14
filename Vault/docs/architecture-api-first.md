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
Radarr/Sonarr/Lidarr (Lookup, Add, Queue — Film/Serie/Musik), TMDB (Suche,
Discover, Recommendations, Credits, Keywords), OMDb (IMDB/RT/Metacritic, ab M5),
Claude (LLM-Begründungen, ab M7), Roon (Now-Playing, Steuerung,
Zonen/Musikauswahl — ab M8, eigene Extension-API).

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

Musik (ab M8 — Roon-Extension-API + Lidarr; Endpunkte vorläufig)
  GET  /music/zones                 Roon-Zonen
  GET  /music/nowplaying            Now-Playing je Zone
  POST /music/transport             Play/Pause/Skip/Lautstärke je Zone
  GET  /music/recommend             Musik-Empfehlungen (getrennt von Film/Serie)
  POST /music/request               → Lidarr add + search (zum Laden)
  POST /music/play                  → in Roon-Zone abspielen (zum Hören)

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
| Lidarr API Key | NAS (Web-UI) | Nein |
| Roon Extension | NAS (Web-UI) | Nein |
| Vault Bearer Token | App + NAS | Ja (einmalig eingeben) |

**TMDB-Key ist ab M4 erforderlich** (Discovery läuft direkt über TMDB). OMDb
ist ab M5 optional. Lidarr und Roon kommen erst mit M8.

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

Beide haben fast deckungsgleiche v3-APIs, Auth per `X-Api-Key`. Discovery läuft
**direkt über TMDB** (siehe Entscheidung unten): Vault sucht in TMDB und fügt
den Treffer per `tmdbId` zu Radarr hinzu; für Serien liefert TMDB über
`external_ids` die `tvdbId` für Sonarr. Ein TMDB-Key ist damit ab M4 nötig.

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

- **Geschmackssignal:** Nach jedem Film fragt die App drei explizite Werte ab:
  **Jannos 0–10-Bewertung**, **Tannos 0–10-Bewertung** und den
  **Tanno-Gruselfaktor 0–20**. Dazu kommen implizite Signale
  (durchgeschaut/abgebrochen, Rewatches, Favoriten). Diese Daten liegen in
  einer eigenen Watch-History/Rating-Tabelle, damit sie auch erhalten bleiben,
  wenn ein Film später aus Jellyfin gelöscht wird.
- **Externe Scores:** Start mit Jellyfins vorhandenen `CommunityRating`
  (≈ IMDB) und `CriticRating` (≈ RT) — kein neuer Key. OMDb (volle
  IMDB/RT/Metacritic per IMDB-ID) kommt optional ab M5 dazu. Kandidaten +
  Genres/Keywords/Cast immer aus TMDB.
- **Engine:** Serverseitig **content-based**, in `recommender.py`: getrennte
  Profile für **Janno**, **Tanno** und **Zusammen** aus hoch bewerteten Titeln
  (Genres/Keywords/Regie/Cast/Jahrzehnt gewichtet) → Kandidaten aus TMDB
  `recommendations`/`discover` → Scoring (Ähnlichkeit × Profil, plus
  Qualitäts-Score, plus Neuheitsbonus). Tannos Gruselfaktor senkt gemeinsame
  und Tanno-Empfehlungen, während Janno-Empfehlungen ihn nur als Warnsignal
  anzeigen.
- **Darstellung:** getrennte Bereiche für **„Für euch beide"**, **„Janno"**
  und **„Tanno"**. Karten zeigen Match-Werte, Begründung, Verfügbarkeit
  (Abspielen/Anfragen), bisherige History-Signale und den Tanno-Gruselfaktor.
  Klar unterscheidbar statt vermischt.
- **LLM (M7):** Claude rankt/begründet die Top-Kandidaten natürlicher.
  Serverseitig, gegen echte TMDB-Titel geerdet.

**Die Schleife:** Empfehlungen im „Für dich neu"-Regal liegen außerhalb der
Bibliothek → jede bekommt je nach Status „Abspielen" oder „Anfragen".
Entdecken → anfragen → herunterladen → ansehen.

## Fachlich: Musik (Roon + Lidarr) — ab M8

Musik wird eine **eigene Säule** parallel zu Film/Serie, mit derselben Schleife:

- **Empfehlungen** (eigener Geschmacks-Profil-Zweig, getrennt von Film/Serie).
- Jede Empfehlung bekommt je nach Verfügbarkeit **„Hören"** (sofort in einer
  Roon-Zone abspielen) oder **„Laden"** (via **Lidarr** add + search).
- **Roon-Steuerung**: Zonen wählen, Now-Playing, Play/Pause/Skip/Lautstärke,
  Musikauswahl direkt aus Vault.

Anbindung über die **bereits vorhandene Roon-Extension-API**. Die genauen
Endpunkte stehen noch nicht fest — sie folgen, sobald die API-Doku vorliegt;
die obigen `/music/*`-Endpunkte sind vorläufig.

---

## Milestone-Zuordnung

**Voraussetzung:** Der Custom-Player muss auf echtem Apple TV bauen und ein MKV
abspielen. Das ist das größte ungeprüfte Risiko — kein zweites unerprobtes
System davor stapeln, bevor der Player lief. Der Player zeigt dafür einfach auf
`/stream/{id}`.

- **M1–M3 — Kern:** vault-api baut `/health`, `/library/*`, `/stream/*` **und
  die Web-Config-UI**. tvOS-App: nur `VaultClient`, keine externen Calls.
- **M4 — Anfragen:** `/request/*`, `/search`; Radarr/Sonarr-Logik im Backend.
  **TMDB-Key erforderlich** (Discovery direkt über TMDB).
- **M5 — Bewertungen & Scores:** `POST …/rating` schreibt die einfache
  Jellyfin-Bewertung; zusätzlich ist ein Vault-eigener Rating-Snapshot geplant
  (`janno_rating`, `tanno_rating`, `tanno_fear_factor`, IDs/Metadaten), der die
  Empfehlungsprofile speist. Score-Anzeige zuerst aus Jellyfin-Feldern, OMDb
  optional dazu.
- **M6 — Empfehlungen:** `/recommend`, `recommender.py`, TMDB Discover und
  profilgetrennte Regale. Die Engine berücksichtigt Janno-/Tanno-Bewertungen,
  Watch-History und Tanno-Gruselfaktor; kein App-Update für neue
  Empfehlungslogik nötig.
- **M7 — LLM:** Claude in `recommender.py`; die App merkt nichts, `/recommend`
  liefert nur bessere Begründungen.
- **M8 — Musik (Roon + Lidarr):** Roon-Steuerung/Now-Playing/Zonen,
  Musikauswahl, Musik-Empfehlungen, Lidarr-Anfragen. Start, sobald die
  Roon-Extension-API-Doku vorliegt.

## Was zuerst gebaut wird (während kein Mac da ist)

vault-api ist **Python und damit sofort baubar und testbar**, auch ohne Apple
TV. Reihenfolge: Projektgerüst (FastAPI + Redis + Docker) → `config.py` +
Web-Config-UI → `services/jellyfin.py` → `/health`, `/library/*`, `/stream/*`.
Die tvOS-Anbindung (`VaultClient` + Player auf `/stream`) folgt am Mac.

## Getroffene Entscheidungen

1. **Discovery:** direkt über **TMDB** (eigener Key, ab M4). Reichstes Material
   für Suche und Empfehlungen; Treffer per `tmdbId`/`tvdbId` an Radarr/Sonarr.
2. **Externe Scores:** zuerst **Jellyfins vorhandene Felder**
   (`CommunityRating`/`CriticRating`), kein neuer Key. **OMDb optional ab M5**.
3. **LLM-Begründungen:** **ja**, als Schicht **ab M7** — algorithmische Engine
   zuerst, Claude formuliert obendrauf.
4. **Empfehlungs-Darstellung:** **zwei getrennte Regale** — „Für dich neu"
   (anfragbar) und „Aus deiner Bibliothek".
5. **Roon:** **volle Integration ab M8** — Steuerung, Zonen, Now-Playing,
   Musikauswahl und Musik-Empfehlungen (Laden via **Lidarr** / Hören via Roon)
   über die vorhandene Roon-Extension-API. Start, sobald deren Doku vorliegt.
