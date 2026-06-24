import deps
from services.homeassistant import HAState


FEED_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Lage Test</title>
    <description>Politik</description>
    <image><url>https://example.test/cover.jpg</url></image>
    <item>
      <title>Episode Eins</title>
      <description><![CDATA[Ein <b>guter</b> Test.]]></description>
      <pubDate>Tue, 23 Jun 2026 10:00:00 +0200</pubDate>
      <itunes:duration xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">00:42:00</itunes:duration>
      <enclosure url="https://example.test/episode-1.mp3" type="audio/mpeg" />
    </item>
  </channel>
</rss>
"""


class FakeResponse:
    def __init__(self, content=FEED_XML, status_code=200):
        self.content = content
        self.status_code = status_code


class FakeHttp:
    def __init__(self):
        self.gets = []

    async def get(self, url, **kwargs):
        self.gets.append((url, kwargs))
        return FakeResponse()


class FakeHA:
    def __init__(self):
        self.played = []
        self.transport = []
        self.seeks = []

    async def play_media(self, entity_id, *, media_content_id, media_content_type="music", enqueue=None):
        self.played.append((entity_id, media_content_id, media_content_type, enqueue))

    async def media_seek(self, entity_id, position_seconds):
        self.seeks.append((entity_id, position_seconds))

    async def states(self, entity_ids):
        return {
            entity_id: HAState(
                entity_id=entity_id,
                state="playing" if entity_id == "media_player.kuche_3" else "idle",
                attributes={
                    "media_title": "Episode Eins",
                    "media_artist": "Lage Test",
                    "media_album_name": "Lage",
                    "media_position": 42,
                    "media_duration": 2520,
                    "entity_picture": "/api/media_player_proxy/media_player.kuche_3",
                },
            )
            for entity_id in entity_ids
        }

    async def media_player_transport(self, entity_id, action):
        self.transport.append((entity_id, action))


def configure_podcasts(store):
    store.update(
        homeassistant={"base_url": "http://ha.local", "api_key": "ha"},
        kiosk_podcasts={
            "feeds": [{"id": "lage", "title": "Lage", "url": "https://example.test/feed.xml"}],
            "players": [
                {"id": "wohnzimmer", "label": "Wohnzimmer", "entity_id": "media_player.wohnzimmer_3"},
                {"id": "kuche", "label": "Küche", "entity_id": "media_player.kuche_3"},
            ],
            "default_player_id": "wohnzimmer",
            "cache_ttl_seconds": 1800,
        },
    )


def test_podcasts_require_bearer(client):
    assert client.get("/podcasts/overview").status_code == 401


def test_podcast_overview_parses_feed_and_accepts_kiosk_token(client, store):
    store.update(kiosk_token="kiosk-pod-token")
    configure_podcasts(store)
    http = FakeHttp()
    client.app.dependency_overrides[deps.get_http] = lambda: http
    try:
        r = client.get("/podcasts/overview", headers={"Authorization": "Bearer kiosk-pod-token"})
    finally:
        client.app.dependency_overrides.pop(deps.get_http, None)

    assert r.status_code == 200
    body = r.json()
    assert body["feeds"][0]["title"] == "Lage"
    assert body["feeds"][0]["episode_count"] == 1
    assert body["episodes"][0]["title"] == "Episode Eins"
    assert body["episodes"][0]["audio_url"] == "https://example.test/episode-1.mp3"
    assert body["episodes"][0]["subtitle"] == "Ein guter Test."
    assert body["players"][0]["entity_id"] == "media_player.wohnzimmer_3"
    assert body["default_player_id"] == "wohnzimmer"


def test_podcast_play_uses_music_assistant_player(client, store, auth):
    configure_podcasts(store)
    http = FakeHttp()
    ha = FakeHA()
    client.app.dependency_overrides[deps.get_http] = lambda: http
    client.app.dependency_overrides[deps.get_homeassistant] = lambda: ha
    try:
        overview = client.get("/podcasts/overview", headers=auth).json()
        episode_id = overview["episodes"][0]["id"]
        r = client.post("/podcasts/play", headers=auth, json={"episode_id": episode_id, "player_id": "kuche"})
    finally:
        client.app.dependency_overrides.pop(deps.get_http, None)
        client.app.dependency_overrides.pop(deps.get_homeassistant, None)

    assert r.status_code == 204
    assert ha.played == [("media_player.kuche_3", "https://example.test/episode-1.mp3", "music", None)]
    assert ha.seeks == []


def test_podcast_progress_is_persisted_and_merged_into_overview_and_feed(client, store, auth):
    configure_podcasts(store)
    http = FakeHttp()
    client.app.dependency_overrides[deps.get_http] = lambda: http
    try:
        overview = client.get("/podcasts/overview", headers=auth).json()
        episode_id = overview["episodes"][0]["id"]
        r = client.post(
            "/podcasts/progress",
            headers=auth,
            json={"episode_id": episode_id, "position_seconds": 137.5, "completed": True},
        )
        overview_after = client.get("/podcasts/overview", headers=auth)
        feed_after = client.get("/podcasts/feed/lage/episodes", headers=auth)
    finally:
        client.app.dependency_overrides.pop(deps.get_http, None)

    assert r.status_code == 204
    episode = overview_after.json()["episodes"][0]
    assert episode["resume_seconds"] == 137.5
    assert episode["completed"] is True
    feed_episode = feed_after.json()[0]
    assert feed_episode["resume_seconds"] == 137.5
    assert feed_episode["completed"] is True


def test_podcast_play_resumes_from_stored_position(client, store, auth):
    configure_podcasts(store)
    http = FakeHttp()
    ha = FakeHA()
    client.app.dependency_overrides[deps.get_http] = lambda: http
    client.app.dependency_overrides[deps.get_homeassistant] = lambda: ha
    try:
        overview = client.get("/podcasts/overview", headers=auth).json()
        episode_id = overview["episodes"][0]["id"]
        client.post(
            "/podcasts/progress",
            headers=auth,
            json={"episode_id": episode_id, "position_seconds": 88, "completed": False},
        )
        r = client.post("/podcasts/play", headers=auth, json={"episode_id": episode_id, "player_id": "kuche"})
    finally:
        client.app.dependency_overrides.pop(deps.get_http, None)
        client.app.dependency_overrides.pop(deps.get_homeassistant, None)

    assert r.status_code == 204
    assert ha.played == [("media_player.kuche_3", "https://example.test/episode-1.mp3", "music", None)]
    assert ha.seeks == [("media_player.kuche_3", 88.0)]


def test_podcast_play_rejects_unknown_player(client, store, auth):
    configure_podcasts(store)
    http = FakeHttp()
    ha = FakeHA()
    client.app.dependency_overrides[deps.get_http] = lambda: http
    client.app.dependency_overrides[deps.get_homeassistant] = lambda: ha
    try:
        overview = client.get("/podcasts/overview", headers=auth).json()
        episode_id = overview["episodes"][0]["id"]
        r = client.post("/podcasts/play", headers=auth, json={"episode_id": episode_id, "player_id": "bad"})
    finally:
        client.app.dependency_overrides.pop(deps.get_http, None)
        client.app.dependency_overrides.pop(deps.get_homeassistant, None)

    assert r.status_code == 404
    assert ha.played == []


def test_podcast_nowplaying_maps_configured_players(client, store, auth):
    configure_podcasts(store)
    ha = FakeHA()
    client.app.dependency_overrides[deps.get_homeassistant] = lambda: ha
    try:
        r = client.get("/podcasts/nowplaying", headers=auth)
    finally:
        client.app.dependency_overrides.pop(deps.get_homeassistant, None)

    assert r.status_code == 200
    body = r.json()
    assert body[1]["player_id"] == "kuche"
    assert body[1]["state"] == "playing"
    assert body[1]["title"] == "Episode Eins"
    assert body[1]["duration"] == 2520


def test_podcast_transport_calls_configured_player(client, store, auth):
    configure_podcasts(store)
    ha = FakeHA()
    client.app.dependency_overrides[deps.get_homeassistant] = lambda: ha
    try:
        r = client.post("/podcasts/transport", headers=auth, json={"player_id": "kuche", "action": "pause"})
    finally:
        client.app.dependency_overrides.pop(deps.get_homeassistant, None)

    assert r.status_code == 204
    assert ha.transport == [("media_player.kuche_3", "pause")]
