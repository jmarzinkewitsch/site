# Immich-Personenfilter Spike

Stand: 2026-06-24

Kurzfazit: Im aktuellen `vault-api` kann der Kiosk Fotos nur aus zwei Quellen
ziehen:

1. `random` via `GET /api/assets/random`
2. ein festes Album via `GET /api/albums/{albumId}`

Der Code in `vault-api/services/immich.py` und `vault-api/routers/photos.py`
kennt noch keinen Personenfilter. Die vorhandene Kiosk-Konfiguration hat nur
`album_id` und `count` (`vault-api/config.py`), deshalb ist ein Personenfilter
derzeit nur als neue Konfigurationsstufe denkbar, nicht als bestehende
Implementierung.

## Belastbare Optionen

### 1) Robuste erste Version: `album_id`

Empfehlung fuer den produktiven Kiosk. Immich liefert dann die Bilder ueber ein
dediziert gepflegtes Album, z. B. `Kiosk` oder `Kiosk-Personen`.

Vorteile:

- stabil und einfach
- keine Abhaengigkeit von eventuell wechselnden Personen-APIs
- gut fuer curated picks oder manuell gepflegte Sammlungen

Relevante Route im Vault:

- `GET /photos/overview` -> ruft intern `GET /api/albums/{albumId}` auf

### 2) Personenfilter, falls Immich ihn in der API sauber hergibt: `person_ids`

Das sollte nur verwendet werden, wenn die Immich-API im konkreten Setup eine
stabile Personenabfrage oder Personen-Zuordnung fuer Assets anbietet.

Gedachte Form im Kiosk:

- `mode: people`
- `person_ids: [...]`
- optionaler Fallback auf Album oder Random, wenn nichts gefunden wird

Wichtig: Im lokalen Code ist noch keine Route dafuer vorhanden. Diese Variante
waere ein Ausbau des vault-api-Services, kein bestehendes Verhalten.

### 3) Fallback-Modus: `random`

Wenn weder `album_id` noch verlassliche Personenfilter verfuegbar sind, bleibt
`random` die einfache Rueckfalloption.

Relevante Route:

- `GET /api/assets/random`

## Vorschlag fuer `mode`

Ein dreistufiges Modell waere am klarsten:

- `mode: random` -> zufaellige Bilder
- `mode: album` -> Bilder aus `album_id`
- `mode: people` -> Bilder aus `person_ids`, mit internem Fallback auf Album
  oder Random

Damit laesst sich die Konfiguration spaeter einfach erweitern, ohne den
bestehenden Foto-Flow umzubauen.

## Konkrete API-Routen

Belegt im Repo:

- `GET /api/server/ping`
- `GET /api/assets/random`
- `GET /api/albums/{albumId}`
- `GET /api/assets/{assetId}/thumbnail?size=preview|thumbnail`

Immich dokumentiert die Server-API als OpenAPI-basiert und verlinkt die
publizierten API-Dokumente unter `api.immich.app`:
https://docs.immich.app/api/

## Empfehlenswerte Schlussfolgerung fuer I2

Fuer den Kiosk sollte zuerst ein dediziertes Immich-Album als robuste Version
geplant werden. Ein Personenfilter ist als Folgeoption sinnvoll, wenn die
Immich-API im Zielsystem eine stabile Personensuche oder Asset-Filterung mit
`person_ids` wirklich hergibt.

Offenes Risiko:

- Die konkrete Personen-Endpoint-Signatur ist im lokalen Repo nicht
  implementiert und sollte vor Umsetzung direkt gegen die aktuelle Immich-API
  geprueft werden.
