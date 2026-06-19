# Roon Jukebox API Documentation

Base URL on the NAS:

```text
http://192.168.0.42:3085
```

The API is a local REST bridge to a paired Roon Core. It does not require HTTP
authentication. Roon itself still requires the extension to be authorized once in
Roon under `Settings -> Extensions -> Jukebox -> Enable`.

All JSON endpoints return `application/json`. Cover images return JPEG bytes.

## Health

### GET `/`

Serves the Jukebox web app.

Open `http://192.168.0.42:3085/` in a browser.

### GET `/api`

Returns a tiny service index.

```bash
curl http://192.168.0.42:3085/api
```

Example response:

```json
{
  "name": "Roon Jukebox API",
  "status_url": "/api/status",
  "albums_url": "/api/albums?offset=0&limit=50",
  "zones_url": "/api/zones"
}
```

### GET `/api/status`

Returns the current Roon connection state.

```bash
curl http://192.168.0.42:3085/api/status
```

Example response:

```json
{
  "connected": true,
  "core_name": "RoonCloud",
  "zone_count": 3
}
```

Fields:

| Field | Type | Description |
|-------|------|-------------|
| `connected` | boolean | Whether the API is paired and connected to Roon Core. |
| `core_name` | string/null | Display name of the connected Roon Core. |
| `zone_count` | number | Number of known Roon zones. |

## Zones and Now Playing

### GET `/api/zones`

Lists all Roon zones with current playback information and outputs.

```bash
curl http://192.168.0.42:3085/api/zones
```

Example response:

```json
{
  "zones": [
    {
      "zone_id": "1601...",
      "display_name": "Wohnzimmer",
      "state": "stopped",
      "now_playing": {
        "title": "Hands Held High",
        "subtitle": "Linkin Park / David Campbell",
        "image_key": "deefe47c...",
        "seek_position": 0,
        "length": 233
      },
      "outputs": [
        {
          "output_id": "1701...",
          "display_name": "Wohnzimmer",
          "volume": null
        }
      ]
    }
  ]
}
```

Use `zone_id` when starting playback or controlling transport. Use `output_id`
for volume changes.

Each output also includes `can_group_with_output_ids` so clients can offer valid
Roon grouping options.

### GET `/api/nowplaying/:zoneId`

Returns now-playing information for one zone.

```bash
curl http://192.168.0.42:3085/api/nowplaying/1601...
```

Example response:

```json
{
  "zone_id": "1601...",
  "state": "playing",
  "now_playing": {
    "title": "Victim of Love (2013 Remaster)",
    "subtitle": "Eagles / Jim Ed Norman",
    "image_key": "ab329cd...",
    "seek_position": 195,
    "length": 250
  }
}
```

## Albums

### GET `/api/search`

Searches Roon using the `search` browser hierarchy.

Query parameters:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | string | required | Search text. |
| `offset` | number | `0` | Zero-based pagination offset. |
| `limit` | number | `50` | Number of results to return. Maximum is `200`. |
| `source` | string | `roon` | Use `roon` for Roon search or `albums` for local album shelf filtering. |

```bash
curl "http://192.168.0.42:3085/api/search?query=coltrane&limit=10"
```

Album-shelf fallback/search:

```bash
curl "http://192.168.0.42:3085/api/search?query=coltrane&source=albums&limit=10"
```

Example response:

```json
{
  "source": "roon",
  "title": "Search",
  "subtitle": null,
  "hint": null,
  "query": "coltrane",
  "results": [
    {
      "item_key": "1:0",
      "title": "Albums",
      "subtitle": "12 results",
      "image_key": null,
      "hint": "list",
      "input_prompt": null,
      "parent_title": "Albums",
      "hierarchy": "search",
      "browser_session_key": "search-...",
      "image_url": null
    }
  ],
  "total": 4,
  "offset": 0,
  "limit": 10,
  "action": "list"
}

```

Notes:

| Field | Description |
|-------|-------------|
| `source` | `roon` means the result came from Roon's search hierarchy. `albums` means local album filtering was used. |
| `results` | Generic Roon search results can be categories, actions, tracks, artists, albums, or other browse items. |
| `fallback_from` | Present when Roon search failed and the API fell back to local album filtering. |
| `hierarchy` / `browser_session_key` | Included on Roon results so the same item can be passed to `POST /api/play`. Roon `item_key` values are scoped to their browser session. |
| `expanded` | `true` when the API automatically opened Roon search categories such as Albums or Tracks and returned their child results. |
| `parent_title` | Present on expanded results and names the Roon search category the hit came from. |

### GET `/api/albums`

Loads albums from the Roon `albums` browser hierarchy for the virtual shelf.

Query parameters:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | string | `""` | Optional local text filter over title and subtitle. |
| `offset` | number | `0` | Zero-based pagination offset. |
| `limit` | number | `50` | Number of albums to return. Maximum is `200`. |

```bash
curl "http://192.168.0.42:3085/api/albums?offset=0&limit=24"
```

Search example:

```bash
curl "http://192.168.0.42:3085/api/albums?query=blue%20train&limit=24"
```

Example response:

```json
{
  "albums": [
    {
      "item_key": "1:0",
      "title": "Blue Train",
      "subtitle": "John Coltrane",
      "image_key": "5352a4...",
      "hint": "list",
      "is_playable": true,
      "image_url": "/api/image/5352a4...?width=500&height=500"
    }
  ],
  "total": 194,
  "offset": 0,
  "limit": 24,
  "query": "",
  "scanned": 24,
  "complete": true
}
```

Notes:

| Field | Description |
|-------|-------------|
| `item_key` | Roon browser key. Pass this to `/api/play` or `/api/album`. |
| `album_index` | Stable album position in the current Roon album sort order. Prefer this for `/api/play`. |
| `image_url` | Relative URL for cover art. Prefix it with the base URL in clients. |
| `total` | Total result count. For filtered searches this is the number of matches found in the scanned range. |
| `scanned` | Number of Roon items inspected. Search scans up to 1000 albums. |
| `complete` | `false` means a search did not scan the entire library. |

### GET `/api/album?itemKey=...`

Loads the Roon browser view for a single album. This is useful for inspecting
available Roon actions before playback or for showing album-level menu items.

```bash
curl "http://192.168.0.42:3085/api/album?itemKey=1%3A0"
```

Using the album index is usually more reliable because Roon `item_key` values
are browser-session scoped:

```bash
curl "http://192.168.0.42:3085/api/album?albumIndex=0"
```

Example response:

```json
{
  "action": "list",
  "title": null,
  "subtitle": null,
  "items": [
    {
      "item_key": "2:0",
      "title": "Play now",
      "subtitle": "",
      "image_key": null,
      "hint": "action",
      "input_prompt": null
    }
  ]
}
```

## Images

### GET `/api/image/:imageKey`

Returns cover art from Roon as JPEG.

Query parameters:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `width` | number | `300` | Requested image width. |
| `height` | number | `300` | Requested image height. |
| `scale` | string | `fit` | Roon image scale mode. |

```bash
curl "http://192.168.0.42:3085/api/image/5352a4...?width=500&height=500" --output cover.jpg
```

Response headers include:

```text
Content-Type: image/jpeg
Cache-Control: public, max-age=86400
```

## Playback

### POST `/api/play`

Starts playback of a Roon browser item, usually an album from `/api/albums`.

Request body:

```json
{
  "zoneId": "1601...",
  "albumIndex": 0
}
```

Example:

```bash
curl -X POST http://192.168.0.42:3085/api/play \
  -H "Content-Type: application/json" \
  -d '{"zoneId":"1601...","albumIndex":0}'
```

`itemKey` is also accepted, but clients should prefer `albumIndex` from
`/api/albums` because Roon browser keys are scoped to a browse session.

Roon search results can also be played when the original search response includes
`hierarchy` and `browser_session_key`:

```bash
curl -X POST http://192.168.0.42:3085/api/play \
  -H "Content-Type: application/json" \
  -d '{
    "zoneId":"1601...",
    "itemKey":"1:3",
    "hierarchy":"search",
    "browserSessionKey":"search-..."
  }'
```

Example response:

```json
{
  "ok": true,
  "action": "play",
  "play_action": "Play now"
}
```

### POST `/api/transport`

Controls playback for a zone.

Transport request body:

```json
{
  "zoneId": "1601...",
  "action": "playpause"
}
```

Valid transport actions:

```text
play
pause
playpause
stop
next
previous
```

Example:

```bash
curl -X POST http://192.168.0.42:3085/api/transport \
  -H "Content-Type: application/json" \
  -d '{"zoneId":"1601...","action":"playpause"}'
```

Example response:

```json
{
  "ok": true
}
```

Volume request body:

```json
{
  "zoneId": "1601...",
  "action": "volume",
  "outputId": "1701...",
  "volume": 35
}
```

Volume uses the output ID, not the zone ID, because Roon volume belongs to an
output.

### GET `/api/queue/:zoneId`

Returns the cached Roon queue subscription for a zone. The app subscribes to the
queue as soon as a zone is discovered.

```bash
curl http://192.168.0.42:3085/api/queue/1601...
```

Example response:

```json
{
  "zone_id": "1601...",
  "items": [
    {
      "queue_item_id": 123,
      "title": "Track title",
      "subtitle": "Artist",
      "detail": "Album",
      "image_key": "abc...",
      "length": 240
    }
  ],
  "count": 1,
  "last_update": "2026-06-11T08:20:00.000Z"
}
```

### POST `/api/queue`

Controls the queue.

```bash
curl -X POST http://192.168.0.42:3085/api/queue \
  -H "Content-Type: application/json" \
  -d '{"zoneId":"1601...","action":"play_from_here","queueItemId":123}'
```

### POST `/api/system`

Global Roon transport helpers.

```bash
curl -X POST http://192.168.0.42:3085/api/system \
  -H "Content-Type: application/json" \
  -d '{"action":"pause_all"}'
```

Valid actions are `pause_all`, `mute_all`, and `unmute_all`.

### POST `/api/output`

Controls output-level features such as mute, relative volume and standby.

```bash
curl -X POST http://192.168.0.42:3085/api/output \
  -H "Content-Type: application/json" \
  -d '{"outputId":"1701...","action":"mute"}'
```

Valid actions:

```text
mute
unmute
volume_relative
volume_step
standby
toggle_standby
convenience_switch
```

### POST `/api/settings`

Changes Roon zone settings.

```bash
curl -X POST http://192.168.0.42:3085/api/settings \
  -H "Content-Type: application/json" \
  -d '{"zoneId":"1601...","shuffle":true,"auto_radio":true,"loop":"disabled"}'
```

Supported fields are `shuffle`, `auto_radio`, and `loop`.

### POST `/api/group`

Groups synchronized Roon outputs.

```bash
curl -X POST http://192.168.0.42:3085/api/group \
  -H "Content-Type: application/json" \
  -d '{"outputIds":["1701...","1701..."]}'
```

The first output's current zone queue is preserved by Roon.

### POST `/api/ungroup`

Ungroups one or more outputs.

```bash
curl -X POST http://192.168.0.42:3085/api/ungroup \
  -H "Content-Type: application/json" \
  -d '{"outputIds":["1701..."]}'
```

### POST `/api/transfer`

Transfers the current queue from one zone to another.

```bash
curl -X POST http://192.168.0.42:3085/api/transfer \
  -H "Content-Type: application/json" \
  -d '{"fromZoneId":"1601...","toZoneId":"1601..."}'
```

### POST `/api/seek`

Seeks to an absolute playback position in seconds.

Request body:

```json
{
  "zoneId": "1601...",
  "seconds": 120
}
```

Example:

```bash
curl -X POST http://192.168.0.42:3085/api/seek \
  -H "Content-Type: application/json" \
  -d '{"zoneId":"1601...","seconds":120}'
```

Example response:

```json
{
  "ok": true
}
```

## Error Responses

Common error responses:

### `400 Bad Request`

Required input is missing or invalid.

```json
{
  "error": "zoneId und itemKey erforderlich"
}
```

### `404 Not Found`

The requested Roon zone does not exist.

```json
{
  "error": "Zone nicht gefunden"
}
```

### `503 Service Unavailable`

The API is running but is not connected to Roon Core.

```json
{
  "error": "Keine Verbindung zur Roon Core"
}
```

### `500 Internal Server Error`

Roon returned an error, or the API could not resolve a Roon browser action.

```json
{
  "error": "Play-Aktion nicht gefunden"
}
```

## Client Notes

For the iPad web app:

1. Load zones from `/api/zones` and let the user pick a default zone.
2. Load shelf pages from `/api/albums?offset=0&limit=24`.
3. Display covers with `baseUrl + album.image_url`.
4. Start playback with `/api/play` using the selected `zone_id` and album `item_key`.
5. Poll `/api/nowplaying/:zoneId` every few seconds for the playback bar.
