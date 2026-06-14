# vault-api

Das Backend aus der Zielarchitektur (siehe
[`../Vault/docs/architecture-api-first.md`](../Vault/docs/architecture-api-first.md)):
**der einzige Endpunkt, den die tvOS-App kennt.** Es orchestriert Jellyfin
(ab M4 auch Radarr/Sonarr/TMDB/…) hinter einer bearer-authentifizierten API und
einer LAN-Web-Config-UI. Alle fremden Keys liegen hier, nie auf dem Apple TV.

**Stand: M1–M7.** `/health`, `/library/*`, `/stream/*` und die Web-Config-UI
(`/admin`) (M1–M3), Anfragen/Suche/TMDB-Discovery (M4), Bewertungen
(0–10 → Jellyfin) und externe Scores (Jellyfin-Felder + optional OMDb) (M5)
sowie `/recommend` mit zwei Regalen und optionalen Claude-Begründungen (M6/M7)
stehen und sind getestet. Musik (M8) folgt.

## Schnellstart (Docker)

```bash
cd vault-api
cp .env.example .env          # optional anpassen
docker compose up --build
```

- API: `http://<host>:8787`
- Config-UI: `http://<host>:8787/admin`

In der Config-UI: Jellyfin (URL, API-Token, User-ID) eintragen, „Verbindung
testen", dann **Bearer-Token erzeugen**. Diesen Token einmalig am Apple TV
eingeben — zusammen mit der vault-api-URL ist das die gesamte App-Konfiguration.

## Lokal ohne Docker

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn main:app --reload --port 8787   # ohne REDIS_URL läuft es cache-los
pytest                                  # Tests: reine Logik + Routen
```

Ohne `REDIS_URL` läuft die API ohne Cache (degradiert, aber voll funktionsfähig).

## Endpunkte

| Methode | Pfad | Auth | Zweck |
|---|---|---|---|
| GET | `/health` | — | Liveness + Status je Dienst |
| GET | `/library/movies` · `/series` | Bearer | Bibliothek (paginiert, gecacht 15 min) |
| GET | `/library/latest?type=Movie\|Series` | Bearer | Neu hinzugefügt (nach Datum, gecacht 15 min) |
| GET | `/library/continue` | Bearer | Weiterschauen |
| GET | `/library/item/{id}` | Bearer | Detail (gecacht 1 h) inkl. externer Scores (OMDb, 7 d, falls Key) |
| GET | `/library/series/{id}/seasons` | Bearer | Staffeln einer Serie (gecacht 1 h) |
| GET | `/library/series/{id}/seasons/{season_id}/episodes` | Bearer | Episoden einer Staffel (gecacht 1 h) |
| POST | `/library/item/{id}/progress` | Bearer | Fortschritt → Jellyfin (invalidiert Cache) |
| POST | `/library/item/{id}/rating` | Bearer | Bewertung 0–10 → Jellyfin (UpdateUserItemData) |
| POST/GET | `/ratings/item/{id}/snapshot` | Bearer | Vault-eigener Janno/Tanno/Fear-Snapshot (SQLite, Jellyfin-unabhängig) |
| GET | `/ratings/snapshots` | Bearer | Alle Vault-Rating-Snapshots für Profile/Empfehlungen |
| GET | `/stream/{id}` | Bearer | frische Direct-Stream-URL (ungecacht) |
| GET | `/discover/movies` · `/series` | Bearer | TMDB-Discovery (gecacht 24 h) |
| GET | `/search?q=` | Bearer | Bibliothek + TMDB, je „playable"/„requestable" |
| GET | `/recommend` | Bearer | Profil-Regale „Für euch beide" / „Jannos Profil" / „Tannos Profil" mit Match-, Personen- und Gruselfaktor-Werten |
| POST | `/request/movie` | Bearer | → Radarr add + search (`tmdbId`) |
| POST | `/request/series` | Bearer | → Sonarr add + search (TMDB→`tvdbId`) |
| GET | `/request/queue` | Bearer | kombinierte Radarr/Sonarr-Download-Queue (gecacht 30 s) |
| GET/POST | `/admin`, `/admin/config`, `/admin/token`, `/admin/test/{service}` | LAN | Konfiguration |

## Architektur des Backends

```
main.py        FastAPI-App + Lifespan (httpx-Client, Cache, Config-Store)
config.py      JSON-Credential-Store (von der Web-UI gefüttert), Env-Bootstrap
auth.py → deps.require_bearer   Bearer-Middleware (Constant-Time-Vergleich)
cache.py       Redis-Wrapper mit TTLs + Invalidierung; degradiert ohne Redis
services/rating_store.py  SQLite-Speicher für Vault-eigene Rating-Snapshots
deps.py        geteilte FastAPI-Dependencies (Store, Cache, Jellyfin/TMDB/*arr, Auth)
models.py      Outward-DTOs (LibraryItem, DiscoverItem, SearchItem, RecommendationResponse, ExternalScores, RequestResult, QueueItem, …)
routers/       health · library · stream · discover · search · recommend · request · admin
services/      jellyfin.py · tmdb.py · recommender.py · anthropic.py · arr.py (Basis) · radarr.py · sonarr.py · omdb.py
web/templates/ admin.html (LAN-Config-UI im Vault-Design)
tests/         pytest: config, cache, jellyfin/tmdb/arr/omdb/recommend-Mapping, Routen (M1–M7)
```

Die Stream-*Bytes* fließen direkt von Jellyfin zur App (LAN); vault-api liefert
nur die URL. Der Jellyfin-`api_key` steckt darin — im reinen LAN-Betrieb
akzeptabel, pro Abruf frisch und nie gecacht.

## Sicherheit

- **Keine fremden Keys auf dem Gerät** — App kennt nur vault-api-URL + Bearer-Token.
- `/admin` ist bewusst **nicht** hinter dem Bearer-Token (er wird dort erst
  erzeugt) und damit für jeden im LAN erreichbar. Für Setups jenseits eines
  Heim-LANs hinter Reverse-Proxy/Authelia (SWAG) setzen.
- `config.json` wird mit `0600` geschrieben und ist gitignoriert.
