import httpx
import pytest

from config import JellyfinConfig
from services.jellyfin import (
    JellyfinError,
    JellyfinService,
    auth_header,
    map_item,
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
    url = stream_url(CFG, "item9", media_source_id="src5")
    assert url == "http://jf.local/Videos/item9/stream?static=true&api_key=tok123&mediaSourceId=src5"


def test_stream_url_without_media_source():
    url = stream_url(CFG, "item9")
    assert "mediaSourceId" not in url
    assert "static=true" in url


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


async def test_report_progress_ok_on_2xx():
    svc = _service_with(lambda r: httpx.Response(204))
    await svc.report_progress("item1", 12.0, False)  # must not raise


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
