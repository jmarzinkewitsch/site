import httpx
import pytest

from config import JellyfinConfig
from services.jellyfin import (
    JellyfinError,
    JellyfinService,
    auth_header,
    map_item,
    audio_tracks_from_item,
    stream_url,
)

pytestmark = pytest.mark.anyio

CFG = JellyfinConfig(base_url="http://jf.local", api_key="tok123", user_id="u1", device_id="dev1")


def test_auth_header_includes_token():
    header = auth_header(CFG)
    assert 'Client="Vault"' in header
    assert 'DeviceId="dev1"' in header
    assert 'Token="tok123"' in header


def test_auth_header_omits_empty_token():
    header = auth_header(JellyfinConfig(base_url="x", user_id="u"))
    assert "Token=" not in header


def test_stream_url_carries_api_key_and_options():
    url = stream_url(CFG, "item9", media_source_id="src5", audio_stream_index=3)
    assert url == "http://jf.local/Videos/item9/stream?static=true&api_key=tok123&mediaSourceId=src5&audioStreamIndex=3"


def test_stream_url_without_media_source():
    url = stream_url(CFG, "item9")
    assert "mediaSourceId" not in url
    assert "static=true" in url


def test_audio_tracks_from_item_prefers_selected_media_source():
    raw = {"MediaSources": [
        {"Id": "a", "MediaStreams": [{"Index": 0, "Type": "Video"}]},
        {"Id": "b", "MediaStreams": [
            {"Index": 1, "Type": "Audio", "Language": "deu", "Codec": "aac", "Channels": 2, "DisplayTitle": "Deutsch"},
            {"Index": 2, "Type": "Audio", "Language": "eng", "Codec": "eac3", "Channels": 6},
        ]},
    ]}
    tracks = audio_tracks_from_item(raw, "b")
    assert [track.index for track in tracks] == [1, 2]
    assert tracks[0].language == "deu"
    assert tracks[0].display_title == "Deutsch"


def test_map_item_movie():
    raw = {
        "Id": "abc",
        "Name": "Dune",
        "Type": "Movie",
        "Overview": "Spice.",
        "ProductionYear": 2021,
        "Genres": ["Sci-Fi"],
        "RunTimeTicks": 9_000_000_000,  # 900 s
        "CommunityRating": 8.0,
        "OfficialRating": "FSK 12",
        "ImageTags": {"Primary": "ptag"},
        "BackdropImageTags": ["btag"],
        "CriticRating": 85,
        "ProviderIds": {"Tmdb": "603", "Imdb": "tt0133093"},
        "UserData": {"Played": False, "PlaybackPositionTicks": 1_200_000_000,
                     "PlayedPercentage": 13.3, "Rating": 7.5},
    }
    item = map_item(raw, "http://jf.local")
    assert item.id == "abc"
    assert item.title == "Dune"
    assert item.runtime_seconds == 900.0
    assert item.resume_position_seconds == 120.0
    assert item.played_percentage == 13.3
    assert item.poster_url == "http://jf.local/Items/abc/Images/Primary?tag=ptag&maxWidth=600&quality=90"
    assert item.backdrop_url == "http://jf.local/Items/abc/Images/Backdrop?tag=btag&maxWidth=1920&quality=90"
    assert item.episode_code is None
    assert item.critic_rating == 85
    assert item.user_rating == 7.5
    assert item.tmdb_id == 603
    assert item.imdb_id == "tt0133093"


def test_map_item_episode_code():
    raw = {"Id": "e1", "Name": "Pilot", "Type": "Episode",
           "ParentIndexNumber": 2, "IndexNumber": 5, "SeriesName": "Show"}
    item = map_item(raw, "http://jf.local")
    assert item.episode_code == "S2 E5"
    assert item.series_name == "Show"


def test_map_item_runtime_falls_back_to_media_source():
    raw = {"Id": "x", "Name": "Y", "Type": "Movie",
           "MediaSources": [{"RunTimeTicks": 600_000_000}]}
    assert map_item(raw, "http://jf.local").runtime_seconds == 60.0


def _service_with(handler) -> JellyfinService:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return JellyfinService(CFG, client)


async def test_movies_maps_items():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/Items"
        assert request.headers["Authorization"].startswith("MediaBrowser")
        return httpx.Response(200, json={"Items": [{"Id": "1", "Name": "A", "Type": "Movie"}]})

    svc = _service_with(handler)
    items = await svc.movies()
    assert len(items) == 1 and items[0].title == "A"


async def test_next_up_uses_jellyfin_shows_next_up_and_maps_items():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["user_id"] = request.url.params.get("userId")
        seen["limit"] = request.url.params.get("limit")
        seen["fields"] = request.url.params.get("fields")
        return httpx.Response(200, json={"Items": [{
            "Id": "e2",
            "Name": "Half Loop",
            "Type": "Episode",
            "SeriesId": "s1",
            "SeriesName": "Severance",
            "ParentIndexNumber": 1,
            "IndexNumber": 2,
            "ImageTags": {"Primary": "ptag"},
            "BackdropImageTags": ["btag"],
            "UserData": {"PlayedPercentage": 25, "PlaybackPositionTicks": 120_000_000},
        }]})

    items = await _service_with(handler).next_up(limit=24)
    assert seen["path"] == "/Shows/NextUp"
    assert seen["user_id"] == "u1"
    assert seen["limit"] == "24"
    assert "ProviderIds" in seen["fields"]
    assert items[0].type == "Episode"
    assert items[0].series_name == "Severance"
    assert items[0].episode_code == "S1 E2"
    assert items[0].played_percentage == 25
    assert items[0].resume_position_seconds == 12
    assert items[0].poster_url == "http://jf.local/Items/e2/Images/Primary?tag=ptag&maxWidth=600&quality=90"


async def test_ping_ok():
    svc = _service_with(lambda r: httpx.Response(200, json={"Version": "10.9"}))
    assert await svc.ping() is True


async def test_error_status_raises():
    svc = _service_with(lambda r: httpx.Response(401, json={}))
    with pytest.raises(JellyfinError) as exc:
        await svc.item("nope")
    assert exc.value.status_code == 401


async def test_item_uses_user_scoped_detail_with_fields():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["fields"] = request.url.params.get("fields")
        return httpx.Response(200, json={
            "Id": "item1",
            "Name": "Dune",
            "Type": "Movie",
            "UserData": {"PlaybackPositionTicks": 1_230_000_000, "PlayedPercentage": 27},
        })

    item = await _service_with(handler).item("item1")
    assert seen["path"] == "/Users/u1/Items/item1"
    assert "MediaSources" in seen["fields"]
    assert item.resume_position_seconds == 123
    assert item.played_percentage == 27


async def test_report_progress_posts_playback_ticks_and_verifies_userdata():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path, request.url.params, request.content))
        if request.method == "POST":
            return httpx.Response(204)
        return httpx.Response(200, json={
            "Id": "item1",
            "Name": "Dune",
            "Type": "Movie",
            "UserData": {"PlaybackPositionTicks": 120_000_000},
        })

    await _service_with(handler).report_progress("item1", 12.0, False, media_source_id="src1")
    import json
    body = json.loads(seen[0][3])
    assert seen[0][1] == "/Sessions/Playing/Progress"
    assert body == {
        "ItemId": "item1",
        "PlaybackPositionTicks": 120_000_000,
        "IsPaused": False,
        "MediaSourceId": "src1",
    }
    assert seen[1][1] == "/Users/u1/Items/item1"


async def test_report_progress_falls_back_to_userdata_when_session_write_is_noop():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.method == "POST" and request.url.path == "/Sessions/Playing/Progress":
            return httpx.Response(204)
        if request.method == "GET" and len(calls) <= 2:
            return httpx.Response(200, json={
                "Id": "item1",
                "Name": "Dune",
                "Type": "Movie",
                "UserData": {"PlaybackPositionTicks": 0},
            })
        if request.method == "POST" and request.url.path == "/UserItems/item1/UserData":
            return httpx.Response(204)
        return httpx.Response(200, json={
            "Id": "item1",
            "Name": "Dune",
            "Type": "Movie",
            "UserData": {"PlaybackPositionTicks": 120_000_000},
        })

    await _service_with(handler).report_progress("item1", 12.0, True)
    import json
    fallback = calls[2]
    assert fallback.url.path == "/UserItems/item1/UserData"
    assert fallback.url.params.get("userId") == "u1"
    assert json.loads(fallback.content) == {"PlaybackPositionTicks": 120_000_000}


async def test_report_progress_falls_back_when_session_endpoint_rejects_inactive_session():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.path == "/Sessions/Playing/Progress":
            return httpx.Response(400, json={"Message": "No active session"})
        if request.url.path == "/UserItems/item1/UserData":
            return httpx.Response(204)
        return httpx.Response(200, json={
            "Id": "item1",
            "Name": "Dune",
            "Type": "Movie",
            "UserData": {"PlaybackPositionTicks": 120_000_000},
        })

    await _service_with(handler).report_progress("item1", 12.0, True)
    assert [request.url.path for request in calls] == [
        "/Sessions/Playing/Progress",
        "/UserItems/item1/UserData",
        "/Users/u1/Items/item1",
    ]


async def test_report_progress_raises_on_error_status():
    svc = _service_with(lambda r: httpx.Response(401, json={}))
    with pytest.raises(JellyfinError) as exc:
        await svc.report_progress("item1", 12.0, False)
    assert exc.value.status_code == 401


async def test_set_rating_posts_userdata():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["user_id"] = request.url.params.get("userId")
        import json
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={})

    await _service_with(handler).set_rating("item9", 8.0)
    assert seen["path"] == "/UserItems/item9/UserData"
    assert seen["user_id"] == "u1"
    assert seen["body"] == {"Rating": 8.0}


async def test_set_rating_raises_on_error_status():
    svc = _service_with(lambda r: httpx.Response(403, json={}))
    with pytest.raises(JellyfinError) as exc:
        await svc.set_rating("item9", 5.0)
    assert exc.value.status_code == 403


def test_mark_played_posts_played_item():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        return httpx.Response(204)

    import asyncio
    asyncio.run(_service_with(handler).mark_played("item9"))
    assert seen == {"method": "POST", "path": "/Users/u1/PlayedItems/item9"}


def test_mark_unplayed_deletes_played_item():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        return httpx.Response(204)

    import asyncio
    asyncio.run(_service_with(handler).mark_unplayed("item9"))
    assert seen == {"method": "DELETE", "path": "/Users/u1/PlayedItems/item9"}


def test_mark_played_raises_on_error_status():
    import asyncio
    svc = _service_with(lambda r: httpx.Response(404, json={}))
    with pytest.raises(JellyfinError) as exc:
        asyncio.run(svc.mark_played("missing"))
    assert exc.value.status_code == 404


async def test_network_error_raises_jellyfin_error():
    def boom(request):
        raise httpx.ConnectError("down", request=request)

    svc = _service_with(boom)
    with pytest.raises(JellyfinError):
        await svc.ping()


def test_map_media_segments_extracts_intro_and_outro():
    from services.jellyfin import map_media_segments

    segments = map_media_segments({"Items": [
        {"Type": "Intro", "StartTicks": 50_000_000, "EndTicks": 125_000_000},
        {"Type": "Outro", "StartTicks": 1_000_000_000, "EndTicks": 1_200_000_000},
        {"Type": "Commercial", "StartTicks": 1, "EndTicks": 2},
    ]})

    assert [segment.type for segment in segments] == ["intro", "outro"]
    assert segments[0].start == 5.0
    assert segments[0].end == 12.5
    assert segments[1].start == 100.0
    assert segments[1].end == 120.0


def test_map_media_segments_empty_when_no_segments():
    from services.jellyfin import map_media_segments

    assert map_media_segments({"Items": []}) == []
    assert map_media_segments({}) == []


async def test_stream_info_includes_media_segments():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        assert request.url.path == "/MediaSegments/item9"
        return httpx.Response(200, json={"Items": [
            {"Type": "Intro", "StartTicks": 10_000_000, "EndTicks": 20_000_000}
        ]})

    info = await _service_with(handler).stream_info("item9")
    assert info.url == "http://jf.local/Videos/item9/stream?static=true&api_key=tok123"
    assert [(segment.type, segment.start, segment.end) for segment in info.segments] == [("intro", 1.0, 2.0)]
    assert seen == ["/MediaSegments/item9"]


async def test_stream_info_gracefully_omits_missing_media_segments():
    svc = _service_with(lambda r: httpx.Response(404, json={}))

    info = await svc.stream_info("item9")

    assert info.segments == []
