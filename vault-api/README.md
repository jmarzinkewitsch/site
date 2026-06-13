# vault-api

Das Backend aus der Zielarchitektur (siehe
[`../Vault/docs/architecture-api-first.md`](../Vault/docs/architecture-api-first.md)):
**der einzige Endpunkt, den die tvOS-App kennt.** Es orchestriert Jellyfin
(ab M4 auch Radarr/Sonarr/TMDB/…) hinter einer bearer-authentifizierten API und
einer LAN-Web-Config-UI. Alle fremden Keys liegen hier, nie auf dem Apple TV.

**Stand: M1–M3-Fundament.** `/health`, `/library/*`, `/stream/*` und die
Web-Config-UI (`/admin`) stehen und sind getestet. Radarr/Sonarr, Discovery,
Empfehlungen, LLM und Musik (M4–M8) folgen.

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
pytest                                  # 32 Tests, reine Logik + Routen
```

Ohne `REDIS_URL` läuft die API ohne Cache (degradiert, aber voll funktionsfähig).

## Endpunkte (M1–M3)

| Methode | Pfad | Auth | Zweck |
|---|---|---|---|
| GET | `/health` | — | Liveness + Status je Dienst |
| GET | `/library/movies` · `/series` | Bearer | Bibliothek (paginiert, gecacht 15 min) |
| GET | `/library/continue` | Bearer | Weiterschauen |
| GET | `/library/item/{id}` | Bearer | Detail (gecacht 1 h) |
| POST | `/library/item/{id}/progress` | Bearer | Fortschritt → Jellyfin (invalidiert Cache) |
| POST | `/library/item/{id}/rating` | Bearer | 501 — kommt mit M5 |
| GET | `/stream/{id}` | Bearer | frische Direct-Stream-URL (ungecacht) |
| GET/POST | `/admin`, `/admin/config`, `/admin/token`, `/admin/test/{service}` | LAN | Konfiguration |

## Architektur des Backends

```
main.py        FastAPI-App + Lifespan (httpx-Client, Cache, Config-Store)
config.py      JSON-Credential-Store (von der Web-UI gefüttert), Env-Bootstrap
auth.py → deps.require_bearer   Bearer-Middleware (Constant-Time-Vergleich)
cache.py       Redis-Wrapper mit TTLs + Invalidierung; degradiert ohne Redis
deps.py        geteilte FastAPI-Dependencies (Store, Cache, Jellyfin, Auth)
models.py      Outward-DTOs (LibraryItem, StreamInfo, …)
routers/       health · library · stream · admin
services/      jellyfin.py (einziger Ort, der Jellyfins Wire-Format kennt)
web/templates/ admin.html (LAN-Config-UI im Vault-Design)
tests/         pytest: config, cache, jellyfin-Mapping, Routen
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
