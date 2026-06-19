# Roon Jukebox API

REST-Bridge zwischen Roon Core und der Jukebox-Web-App.  
Läuft als Docker-Container auf dem NAS (jancloud).

## Setup

### 1. Repository auf das NAS kopieren

```bash
scp -r ./roon-jukebox-api jan@jancloud:/opt/docker/roon-jukebox-api
```

### 2. Container starten

```bash
cd /opt/docker/roon-jukebox-api
docker compose up -d
```

### 3. Extension in Roon autorisieren

In der Roon-App: **Settings → Extensions → Jukebox → Enable**

Das ist einmalig nötig. Danach verbindet sich die Extension automatisch.

---

## Endpoints

Ausfuehrliche API-Doku: [API.md](./API.md)

| Methode | Pfad | Beschreibung |
|---------|------|--------------|
| GET | `/api/status` | Verbindungsstatus zur Roon Core |
| GET | `/api/zones` | Alle Zonen inkl. Now-Playing |
| GET | `/api/nowplaying/:zoneId` | Now-Playing einer Zone |
| GET | `/api/albums?query=&offset=0&limit=50` | Alben fuer das virtuelle Regal laden |
| GET | `/api/album?itemKey=...` | Album-Details / Roon-Aktionen laden |
| GET | `/api/image/:imageKey?width=300&height=300` | Cover-Art als JPEG |
| POST | `/api/play` | Album abspielen `{ zoneId, itemKey }` |
| POST | `/api/transport` | Steuern `{ zoneId, action }` |
| POST | `/api/seek` | Springen `{ zoneId, seconds }` |

### Transport-Aktionen

```
play | pause | playpause | stop | next | previous
```

Lautstärke: `{ zoneId, action: "volume", outputId, volume: 50 }`

---

## Beispiele

```bash
# Status prüfen
curl http://jancloud:3085/api/status

# Alle Zonen anzeigen
curl http://jancloud:3085/api/zones

# Erste Regal-Seite laden
curl "http://jancloud:3085/api/albums?limit=24"

# Album suchen
curl "http://jancloud:3085/api/albums?query=blue%20train"

# Play/Pause auf Zone
curl -X POST http://jancloud:3085/api/transport \
  -H "Content-Type: application/json" \
  -d '{"zoneId": "DEINE_ZONE_ID", "action": "playpause"}'
```

---

## Home Assistant – iFrame Panel

In `configuration.yaml`:

```yaml
panel_iframe:
  jukebox:
    title: "Jukebox"
    url: "http://jancloud:3085"
    icon: mdi:turntable
    require_admin: false
```

---

## Umgebungsvariablen

| Variable | Default | Beschreibung |
|----------|---------|--------------|
| `PORT` | `3085` | HTTP-Port der API |
| `ROON_HOST` | – | Roon Core IP (leer = Autodiscovery) |
| `ROON_PORT` | `9100` | Roon Core Port |

> **Hinweis zu Autodiscovery:** Der Container muss `network_mode: host` nutzen,
> damit Roon-Discovery (UDP Broadcast) funktioniert. Das ist in docker-compose.yml
> bereits so gesetzt.
