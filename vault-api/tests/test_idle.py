"""Tests for GET /kiosk/idle/overview (Paket A3 — Idle-Infoboard)."""
from __future__ import annotations

import deps
from models import LibraryItem, NewsHeadline, PhotoItem
from services.homeassistant import HAState


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class FakeIdleHomeAssistant:
    """Minimal HA double for the idle endpoint."""

    def __init__(self, *, raise_on_state: bool = False, raise_on_forecasts: bool = False):
        self._raise_state = raise_on_state
        self._raise_forecasts = raise_on_forecasts

    async def state(self, entity_id: str) -> HAState | None:
        if self._raise_state:
            raise RuntimeError("HA down")
        return HAState(
            entity_id=entity_id,
            state="partlycloudy",
            attributes={"temperature": 18.5},
        )

    async def weather_forecasts(self, entity_id: str, *, forecast_type: str, timeout: float | None = None):
        if self._raise_forecasts:
            raise RuntimeError("forecast down")
        if forecast_type == "hourly":
            return [
                {"datetime": "2026-06-24T16:00:00+02:00", "condition": "cloudy", "temperature": 17},
                {"datetime": "2026-06-24T17:00:00+02:00", "condition": "rainy", "temperature": 16},
                {"datetime": "2026-06-24T18:00:00+02:00", "condition": "cloudy", "temperature": 15},
                {"datetime": "2026-06-24T19:00:00+02:00", "condition": "clear-night", "temperature": 14},
            ]
        # daily
        return [
            {"datetime": "2026-06-25T00:00:00+02:00", "condition": "sunny", "temperature": 22},
            {"datetime": "2026-06-26T00:00:00+02:00", "condition": "rainy", "temperature": 19},
            {"datetime": "2026-06-27T00:00:00+02:00", "condition": "partlycloudy", "temperature": 20},
        ]

    async def states(self, entity_ids):
        """Used by podcast nowplaying path."""
        result = {}
        for eid in entity_ids:
            result[eid] = HAState(
                entity_id=eid,
                state="playing",
                attributes={
                    "media_title": "Podcast Folge 42",
                    "media_artist": "Das Podcast-Team",
                    "entity_picture": "/api/media_player_proxy/wohnzimmer",
                    "media_position": 120.0,
                    "media_duration": 3600.0,
                },
            )
        return result


class FakeIdleJellyfin:
    def __init__(self, *, raise_on_latest: bool = False):
        self._raise = raise_on_latest

    async def latest(self, include_type: str, limit: int = 8):
        if self._raise:
            raise RuntimeError("Jellyfin down")
        if include_type == "Movie":
            return [
                LibraryItem(
                    id="m1",
                    type="Movie",
                    title="Blade Runner 2049",
                    year=2017,
                    genres=["Sci-Fi", "Drama"],
                    backdrop_url="http://jf/Items/m1/Images/Backdrop",
                )
            ]
        # Series — return two items with same series_id to test deduplication
        return [
            LibraryItem(
                id="e1",
                type="Episode",
                title="Pilot",
                series_name="Severance",
                episode_code="S01E01",
                series_id="sv1",
                backdrop_url="http://jf/Items/e1/Images/Backdrop",
            ),
            LibraryItem(
                id="e2",
                type="Episode",
                title="Good News About Hell",
                series_name="Severance",
                episode_code="S01E02",
                series_id="sv1",
                backdrop_url="http://jf/Items/e2/Images/Backdrop",
            ),
        ]


class FakeIdleImmichHttp:
    """Used to override get_http for the /kiosk/idle/overview call."""

    def __init__(self):
        self.gets = []

    async def get(self, url, *, headers=None, params=None, **kwargs):
        self.gets.append(url)
        if "/api/assets/random" in url:
            return _FakeResp(
                [{"id": "photo-1", "originalFileName": "test.jpg", "fileCreatedAt": "2026-06-24T10:00:00Z"}]
            )
        # news feed — return minimal RSS
        return _FakeResp(
            b"""<?xml version="1.0"?>
<rss version="2.0"><channel>
  <item><title>Schlagzeile 1</title><description>Zusammenfassung 1</description><link>https://example.com/1</link></item>
</channel></rss>""",
            content_type="application/rss+xml",
        )


class _FakeResp:
    def __init__(self, payload_or_content, *, content_type: str = "application/json"):
        if isinstance(payload_or_content, bytes):
            self.content = payload_or_content
            self._payload = None
        else:
            self._payload = payload_or_content
            self.content = b""
        self.status_code = 200
        self.headers = {"content-type": content_type}

    def json(self):
        return self._payload


class FakeRoonService:
    """Simulates a Roon zone that is currently playing music."""

    def __init__(self, *, playing: bool = True):
        self._playing = playing

    async def get_json(self, path: str):
        if path == "zones":
            if self._playing:
                return {
                    "zones": [
                        {
                            "zone_id": "z1",
                            "state": "playing",
                            "now_playing": {
                                "three_line": {"line1": "Kind of Blue", "line2": "Miles Davis"},
                                "image_key": "img-abc123",
                                "seek_position": 42,
                                "length": 330,
                            },
                        }
                    ]
                }
            return {"zones": [{"zone_id": "z1", "state": "paused"}]}
        return {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _configure(store):
    """Set up minimal config for the idle endpoint."""
    store.update(
        kiosk_token="kiosk-idle-token",
        homeassistant={"base_url": "http://ha.local", "api_key": "hatoken"},
        jellyfin={"base_url": "http://jf.local", "api_key": "jfkey", "user_id": "u1"},
        immich={"base_url": "http://immich.local", "api_key": "imkey"},
        kiosk_news={
            "per_feed": 1,
            "feeds": [{"id": "zeit", "label": "ZEIT", "url": "https://newsfeed.zeit.de/all"}],
        },
        kiosk_photos={"mode": "random", "count": 4},
    )


_KIOSK_AUTH = {"Authorization": "Bearer kiosk-idle-token"}
_BEARER_AUTH = {"Authorization": "Bearer test-bearer-token"}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_idle_overview_requires_auth(client):
    r = client.get("/kiosk/idle/overview")
    assert r.status_code == 401


def test_idle_overview_accepts_bearer(client, store):
    _configure(store)
    client.app.dependency_overrides[deps.get_homeassistant] = lambda: FakeIdleHomeAssistant()
    client.app.dependency_overrides[deps.get_jellyfin] = lambda: FakeIdleJellyfin()
    client.app.dependency_overrides[deps.get_http] = lambda: FakeIdleImmichHttp()
    client.app.dependency_overrides[deps.get_optional_roon] = lambda: None
    try:
        r = client.get("/kiosk/idle/overview", headers=_BEARER_AUTH)
    finally:
        client.app.dependency_overrides.pop(deps.get_homeassistant, None)
        client.app.dependency_overrides.pop(deps.get_jellyfin, None)
        client.app.dependency_overrides.pop(deps.get_http, None)
        client.app.dependency_overrides.pop(deps.get_optional_roon, None)
    assert r.status_code == 200


def test_idle_overview_full_response(client, store):
    """Happy path: all sources deliver data — verify full mapping."""
    _configure(store)
    client.app.dependency_overrides[deps.get_homeassistant] = lambda: FakeIdleHomeAssistant()
    client.app.dependency_overrides[deps.get_jellyfin] = lambda: FakeIdleJellyfin()
    client.app.dependency_overrides[deps.get_http] = lambda: FakeIdleImmichHttp()
    client.app.dependency_overrides[deps.get_optional_roon] = lambda: FakeRoonService(playing=True)
    try:
        r = client.get("/kiosk/idle/overview", headers=_KIOSK_AUTH)
    finally:
        client.app.dependency_overrides.pop(deps.get_homeassistant, None)
        client.app.dependency_overrides.pop(deps.get_jellyfin, None)
        client.app.dependency_overrides.pop(deps.get_http, None)
        client.app.dependency_overrides.pop(deps.get_optional_roon, None)

    assert r.status_code == 200
    body = r.json()

    # weather
    assert body["weather"] is not None
    assert body["weather"]["condition"] == "partlycloudy"
    assert body["weather"]["temperature"] == 18.5
    forecast = body["weather"]["forecast"]
    assert len(forecast) >= 1
    assert "when" in forecast[0]
    assert "condition" in forecast[0]
    assert "temperature" in forecast[0]

    # film
    assert body["film"] is not None
    assert body["film"]["title"] == "Blade Runner 2049"
    assert body["film"]["type"] == "Movie"
    assert body["film"]["backdrop_url"] == "/kiosk/media/image/m1?kind=backdrop"
    assert body["film"]["subtitle"] == "2017 · Sci-Fi, Drama"
    assert body["film"]["reason"] is None

    # series — deduplicated to one item even though both episodes have series_id=sv1
    assert body["series"] is not None
    assert body["series"]["title"] == "Pilot"
    assert body["series"]["type"] == "Series"
    assert body["series"]["backdrop_url"] == "/kiosk/media/image/e1?kind=backdrop"

    # headlines
    assert len(body["headlines"]) >= 1
    assert body["headlines"][0]["title"] == "Schlagzeile 1"

    # photos
    assert "/photos/image/photo-1" in body["photos"]

    # now_playing — Roon is playing
    np = body["now_playing"]
    assert np is not None
    assert np["kind"] == "music"
    assert np["title"] == "Kind of Blue"
    assert np["subtitle"] == "Miles Davis"
    assert np["image_url"] == "/music/image/img-abc123"
    assert np["position"] == 42
    assert np["duration"] == 330


def test_idle_overview_series_deduplication(client, store):
    """Two episodes with the same series_id must yield only one series card."""
    _configure(store)

    class DedupeJellyfin(FakeIdleJellyfin):
        async def latest(self, include_type, limit=8):
            if include_type == "Movie":
                return []
            # Three episodes, all same series_id
            return [
                LibraryItem(
                    id=f"e{i}", type="Episode", title=f"Ep {i}",
                    series_name="Silo", episode_code=f"S01E0{i}",
                    series_id="silo1",
                    backdrop_url=f"http://jf/e{i}",
                )
                for i in range(3)
            ]

    client.app.dependency_overrides[deps.get_homeassistant] = lambda: FakeIdleHomeAssistant()
    client.app.dependency_overrides[deps.get_jellyfin] = lambda: DedupeJellyfin()
    client.app.dependency_overrides[deps.get_http] = lambda: FakeIdleImmichHttp()
    client.app.dependency_overrides[deps.get_optional_roon] = lambda: None
    try:
        r = client.get("/kiosk/idle/overview", headers=_KIOSK_AUTH)
    finally:
        client.app.dependency_overrides.pop(deps.get_homeassistant, None)
        client.app.dependency_overrides.pop(deps.get_jellyfin, None)
        client.app.dependency_overrides.pop(deps.get_http, None)
        client.app.dependency_overrides.pop(deps.get_optional_roon, None)

    assert r.status_code == 200
    body = r.json()
    # Exactly one series card
    assert body["series"] is not None
    assert body["series"]["title"] == "Ep 0"


def test_idle_overview_source_failure_yields_null_field(client, store):
    """If Jellyfin (film/series) raises, film and series are null — HTTP 200."""
    _configure(store)
    client.app.dependency_overrides[deps.get_homeassistant] = lambda: FakeIdleHomeAssistant()
    client.app.dependency_overrides[deps.get_jellyfin] = lambda: FakeIdleJellyfin(raise_on_latest=True)
    client.app.dependency_overrides[deps.get_http] = lambda: FakeIdleImmichHttp()
    client.app.dependency_overrides[deps.get_optional_roon] = lambda: None
    try:
        r = client.get("/kiosk/idle/overview", headers=_KIOSK_AUTH)
    finally:
        client.app.dependency_overrides.pop(deps.get_homeassistant, None)
        client.app.dependency_overrides.pop(deps.get_jellyfin, None)
        client.app.dependency_overrides.pop(deps.get_http, None)
        client.app.dependency_overrides.pop(deps.get_optional_roon, None)

    assert r.status_code == 200
    body = r.json()
    assert body["film"] is None
    assert body["series"] is None
    # weather and headlines should still come through
    assert body["weather"] is not None


def test_idle_overview_weather_failure_yields_null(client, store):
    """If HA state raises, weather is null — rest of response is 200."""
    _configure(store)
    client.app.dependency_overrides[deps.get_homeassistant] = lambda: FakeIdleHomeAssistant(raise_on_state=True)
    client.app.dependency_overrides[deps.get_jellyfin] = lambda: FakeIdleJellyfin()
    client.app.dependency_overrides[deps.get_http] = lambda: FakeIdleImmichHttp()
    client.app.dependency_overrides[deps.get_optional_roon] = lambda: None
    try:
        r = client.get("/kiosk/idle/overview", headers=_KIOSK_AUTH)
    finally:
        client.app.dependency_overrides.pop(deps.get_homeassistant, None)
        client.app.dependency_overrides.pop(deps.get_jellyfin, None)
        client.app.dependency_overrides.pop(deps.get_http, None)
        client.app.dependency_overrides.pop(deps.get_optional_roon, None)

    assert r.status_code == 200
    body = r.json()
    assert body["weather"] is None


def test_idle_overview_headlines_passthrough(client, store):
    """Headlines from the news service end up directly in headlines[]."""
    _configure(store)
    client.app.dependency_overrides[deps.get_homeassistant] = lambda: FakeIdleHomeAssistant()
    client.app.dependency_overrides[deps.get_jellyfin] = lambda: FakeIdleJellyfin()
    client.app.dependency_overrides[deps.get_http] = lambda: FakeIdleImmichHttp()
    client.app.dependency_overrides[deps.get_optional_roon] = lambda: None
    try:
        r = client.get("/kiosk/idle/overview", headers=_KIOSK_AUTH)
    finally:
        client.app.dependency_overrides.pop(deps.get_homeassistant, None)
        client.app.dependency_overrides.pop(deps.get_jellyfin, None)
        client.app.dependency_overrides.pop(deps.get_http, None)
        client.app.dependency_overrides.pop(deps.get_optional_roon, None)

    assert r.status_code == 200
    headlines = r.json()["headlines"]
    assert isinstance(headlines, list)
    assert all("title" in h for h in headlines)
    assert all("summary" in h for h in headlines)
    assert all("source" in h for h in headlines)
    assert all("link" in h for h in headlines)


def test_idle_overview_roon_not_configured_falls_back_to_podcast(client, store):
    """When Roon is None, a playing HA media player yields kind=podcast."""
    _configure(store)
    client.app.dependency_overrides[deps.get_homeassistant] = lambda: FakeIdleHomeAssistant()
    client.app.dependency_overrides[deps.get_jellyfin] = lambda: FakeIdleJellyfin()
    client.app.dependency_overrides[deps.get_http] = lambda: FakeIdleImmichHttp()
    client.app.dependency_overrides[deps.get_optional_roon] = lambda: None
    try:
        r = client.get("/kiosk/idle/overview", headers=_KIOSK_AUTH)
    finally:
        client.app.dependency_overrides.pop(deps.get_homeassistant, None)
        client.app.dependency_overrides.pop(deps.get_jellyfin, None)
        client.app.dependency_overrides.pop(deps.get_http, None)
        client.app.dependency_overrides.pop(deps.get_optional_roon, None)

    assert r.status_code == 200
    np = r.json()["now_playing"]
    assert np is not None
    assert np["kind"] == "podcast"
    assert np["title"] == "Podcast Folge 42"
    assert np["subtitle"] == "Das Podcast-Team"


def test_idle_overview_immich_not_configured_photos_empty(client, store):
    """When Immich is not configured, photos is an empty list — not null."""
    store.update(
        kiosk_token="kiosk-idle-token",
        homeassistant={"base_url": "http://ha.local", "api_key": "hatoken"},
        jellyfin={"base_url": "http://jf.local", "api_key": "jfkey", "user_id": "u1"},
        # no immich config
    )
    client.app.dependency_overrides[deps.get_homeassistant] = lambda: FakeIdleHomeAssistant()
    client.app.dependency_overrides[deps.get_jellyfin] = lambda: FakeIdleJellyfin()
    client.app.dependency_overrides[deps.get_optional_roon] = lambda: None
    try:
        r = client.get("/kiosk/idle/overview", headers=_KIOSK_AUTH)
    finally:
        client.app.dependency_overrides.pop(deps.get_homeassistant, None)
        client.app.dependency_overrides.pop(deps.get_jellyfin, None)
        client.app.dependency_overrides.pop(deps.get_optional_roon, None)

    assert r.status_code == 200
    assert r.json()["photos"] == []
