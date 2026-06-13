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
        "UserData": {"Played": False, "PlaybackPositionTicks": 1_200_000_000, "PlayedPercentage": 13.3},
    }
    item = map_item(raw, "http://jf.local")
    assert item.id == "abc"
    assert item.title == "Dune"
    assert item.runtime_seconds == 900.0
    assert item.resume_position_seconds == 120.0
    assert item.played_percentage == 13.3
    assert item.poster_url == "http://jf.local/Items/abc/Images/Primary?tag=ptag"
    assert item.backdrop_url == "http://jf.local/Items/abc/Images/Backdrop?tag=btag"
    assert item.episode_code is None


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


async def test_network_error_raises_jellyfin_error():
    def boom(request):
        raise httpx.ConnectError("down", request=request)

    svc = _service_with(boom)
    with pytest.raises(JellyfinError):
        await svc.ping()
