import httpx
import pytest

from config import JellyfinConfig
from services.jellyfin import (
    JellyfinError,
    JellyfinService,
    auth_header,
    map_item,
    map_remote_subtitle,
    audio_tracks_from_item,
    subtitle_tracks_from_item,
    trickplay_from_item,
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


def test_subtitle_tracks_marks_external_with_delivery_url():
    raw = {"MediaSources": [
        {"Id": "src5", "MediaStreams": [
            {"Index": 2, "Type": "Subtitle", "Codec": "subrip", "Language": "eng",
             "DisplayTitle": "English (embedded)", "IsExternal": False},
            {"Index": 3, "Type": "Subtitle", "Codec": "subrip", "Language": "ger",
             "DisplayTitle": "Deutsch (OpenSubtitles)", "IsExternal": True},
        ]},
    ]}
    tracks = subtitle_tracks_from_item(CFG, raw, "item9", "src5")
    assert [t.index for t in tracks] == [2, 3]
    embedded, external = tracks
    assert embedded.is_external is False
    assert embedded.delivery_url is None
    assert external.is_external is True
    assert external.delivery_url == (
        "http://jf.local/Videos/item9/src5/Subtitles/3/0/Stream.srt?api_key=tok123"
    )


def test_subtitle_tracks_skips_bitmap_codecs():
    raw = {"MediaStreams": [
        {"Index": 1, "Type": "Subtitle", "Codec": "pgssub", "IsExternal": False},
        {"Index": 2, "Type": "Subtitle", "Codec": "ass", "IsExternal": False},
    ]}
    tracks = subtitle_tracks_from_item(CFG, raw, "item9")
    assert [t.index for t in tracks] == [2]


def test_subtitle_delivery_url_defaults_source_to_item_id():
    raw = {"MediaStreams": [
        {"Index": 4, "Type": "Subtitle", "Codec": "srt", "IsExternal": True},
    ]}
    tracks = subtitle_tracks_from_item(CFG, raw, "item9")
    assert tracks[0].delivery_url == (
        "http://jf.local/Videos/item9/item9/Subtitles/4/0/Stream.srt?api_key=tok123"
    )


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
def test_map_item_logo_own_tag():
    # A movie/series that carries its own Logo ImageTag should get a logo_url
    # pointing at /Images/Logo with the right tag and size constraints.
    raw = {
        "Id": "mov1",
        "Name": "Dune",
        "Type": "Movie",
        "ImageTags": {"Primary": "ptag", "Logo": "ltag123"},
    }
    item = map_item(raw, "http://jf.local")
    assert item.logo_url is not None
    assert "/Images/Logo" in item.logo_url
    assert "ltag123" in item.logo_url
    assert "maxWidth=800" in item.logo_url


def test_map_item_logo_parent_fallback():
    # An episode has no own Logo tag; the parent-series logo is exposed via
    # ParentLogoItemId + ParentLogoImageTag and should be used instead.
    raw = {
        "Id": "ep1",
        "Name": "Pilot",
        "Type": "Episode",
        "ImageTags": {"Primary": "ptag"},
        "ParentLogoItemId": "series42",
        "ParentLogoImageTag": "slogtag",
    }
    item = map_item(raw, "http://jf.local")
    assert item.logo_url is not None
    assert "series42" in item.logo_url
    assert "slogtag" in item.logo_url
    assert "/Images/Logo" in item.logo_url


def test_map_item_logo_missing_yields_none():
    # An item with neither own logo nor parent logo pointers gets logo_url=None.
    raw = {
        "Id": "mov2",
        "Name": "No Logo Movie",
        "Type": "Movie",
        "ImageTags": {"Primary": "ptag"},
    }
    item = map_item(raw, "http://jf.local")
    assert item.logo_url is None




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


# ---------------------------------------------------------------------------
# trickplay_from_item
# ---------------------------------------------------------------------------

def _make_trickplay_item(
    source_id: str = "src1",
    width_key: str = "320",
    data: dict | None = None,
) -> dict:
    """Minimal item dict with a well-formed Trickplay blob."""
    if data is None:
        data = {
            "Width": 320,
            "Height": 180,
            "TileWidth": 10,
            "TileHeight": 10,
            "ThumbnailCount": 150,
            "Interval": 10000,
            "Bandwidth": 12345,
        }
    return {
        "MediaSources": [{"Id": source_id}],
        "Trickplay": {source_id: {width_key: data}},
    }


def test_trickplay_from_item_happy_path():
    item = _make_trickplay_item()
    info = trickplay_from_item(CFG, item, "item9", "src1")
    assert info is not None
    assert info.interval == 10000
    assert info.tile_width == 10
    assert info.tile_height == 10
    assert info.thumbnail_width == 320
    assert info.thumbnail_height == 180
    assert info.thumbnail_count == 150
    # URL carries the literal placeholder and the api_key
    assert "{index}" in info.tile_url_template
    assert "tok123" in info.tile_url_template
    assert "http://jf.local/Videos/item9/Trickplay/320/" in info.tile_url_template
    assert info.tile_url_template == "http://jf.local/Videos/item9/Trickplay/320/{index}.jpg?api_key=tok123"


def test_trickplay_from_item_picks_largest_width():
    """When multiple width keys exist, the largest should win."""
    item = {
        "MediaSources": [{"Id": "src1"}],
        "Trickplay": {
            "src1": {
                "160": {"Width": 160, "Height": 90, "TileWidth": 5, "TileHeight": 5, "ThumbnailCount": 50, "Interval": 5000},
                "320": {"Width": 320, "Height": 180, "TileWidth": 10, "TileHeight": 10, "ThumbnailCount": 150, "Interval": 10000},
            }
        },
    }
    info = trickplay_from_item(CFG, item, "item9", "src1")
    assert info is not None
    assert info.thumbnail_width == 320
    assert "Trickplay/320/" in info.tile_url_template


def test_trickplay_from_item_falls_back_to_first_source_if_id_not_found():
    """If the resolved source_id isn't in the Trickplay map, use the first entry."""
    item = {
        "MediaSources": [{"Id": "src1"}],
        "Trickplay": {
            "other_src": {
                "320": {"Width": 320, "Height": 180, "TileWidth": 10, "TileHeight": 10, "ThumbnailCount": 50, "Interval": 5000},
            }
        },
    }
    info = trickplay_from_item(CFG, item, "item9", "src1")
    assert info is not None
    assert info.thumbnail_width == 320


def test_trickplay_from_item_missing_trickplay_returns_none():
    item = {"MediaSources": [{"Id": "src1"}]}
    assert trickplay_from_item(CFG, item, "item9") is None


def test_trickplay_from_item_empty_trickplay_returns_none():
    item = {"MediaSources": [{"Id": "src1"}], "Trickplay": {}}
    assert trickplay_from_item(CFG, item, "item9") is None


def test_trickplay_from_item_non_dict_trickplay_returns_none():
    item = {"MediaSources": [{"Id": "src1"}], "Trickplay": None}
    assert trickplay_from_item(CFG, item, "item9") is None


def test_trickplay_from_item_zero_interval_returns_none():
    """An interval of 0 makes scrubbing impossible — must return None."""
    item = _make_trickplay_item(data={
        "Width": 320, "Height": 180, "TileWidth": 10, "TileHeight": 10,
        "ThumbnailCount": 50, "Interval": 0,
    })
    assert trickplay_from_item(CFG, item, "item9") is None


def test_trickplay_from_item_zero_tile_dimensions_returns_none():
    """TileWidth=0 or TileHeight=0 means the sheet layout is broken — must return None."""
    item = _make_trickplay_item(data={
        "Width": 320, "Height": 180, "TileWidth": 0, "TileHeight": 10,
        "ThumbnailCount": 50, "Interval": 5000,
    })
    assert trickplay_from_item(CFG, item, "item9") is None


def test_trickplay_from_item_tile_url_template_contains_literal_index_placeholder():
    """The {index} placeholder must survive in the returned string (not be formatted away)."""
    item = _make_trickplay_item()
    info = trickplay_from_item(CFG, item, "item9", "src1")
    assert info is not None
    # Must contain exactly the literal text "{index}", not a number
    assert "{index}" in info.tile_url_template
    assert info.tile_url_template.endswith("{index}.jpg?api_key=tok123")


# ---------------------------------------------------------------------------
# map_remote_subtitle
# ---------------------------------------------------------------------------

def test_map_remote_subtitle_happy_path():
    raw = {
        "Id": "opensubtitles/123456",
        "ProviderName": "OpenSubtitles",
        "Name": "Movie.de.srt",
        "Format": "srt",
        "Language": "ger",
        "DownloadCount": 9876,
        "CommunityRating": 8.5,
        "IsHashMatch": True,
        "Comment": "Hash match",
    }
    result = map_remote_subtitle(raw)
    assert result is not None
    assert result.id == "opensubtitles/123456"
    assert result.provider_name == "OpenSubtitles"
    assert result.name == "Movie.de.srt"
    assert result.format == "srt"
    assert result.language == "ger"
    assert result.download_count == 9876
    assert result.community_rating == 8.5
    assert result.is_hash_match is True
    assert result.comment == "Hash match"


def test_map_remote_subtitle_missing_id_returns_none():
    """Entries without an Id can't be downloaded and must be skipped."""
    assert map_remote_subtitle({"ProviderName": "OpenSubtitles"}) is None
    assert map_remote_subtitle({}) is None


def test_map_remote_subtitle_empty_id_returns_none():
    assert map_remote_subtitle({"Id": ""}) is None
    assert map_remote_subtitle({"Id": None}) is None


def test_map_remote_subtitle_tolerates_missing_optional_fields():
    """All optional fields may be absent — only id is required."""
    result = map_remote_subtitle({"Id": "abc"})
    assert result is not None
    assert result.id == "abc"
    assert result.provider_name is None
    assert result.download_count is None
    assert result.is_hash_match is None


def test_map_remote_subtitle_non_dict_returns_none():
    assert map_remote_subtitle(None) is None  # type: ignore[arg-type]
    assert map_remote_subtitle("bad") is None  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# search_subtitles
# ---------------------------------------------------------------------------

async def test_search_subtitles_merges_and_dedupes_across_languages():
    """Results from multiple languages are merged; duplicate ids are dropped
    (first occurrence wins). The merged list should include all unique entries."""
    responses = {
        "/Items/item9/RemoteSearch/Subtitles/ger": [
            {"Id": "p/1", "ProviderName": "OpenSubtitles", "Language": "ger",
             "DownloadCount": 100, "IsHashMatch": False},
            {"Id": "p/2", "ProviderName": "OpenSubtitles", "Language": "ger",
             "DownloadCount": 50, "IsHashMatch": True},
        ],
        "/Items/item9/RemoteSearch/Subtitles/eng": [
            {"Id": "p/1", "ProviderName": "OpenSubtitles", "Language": "eng",
             "DownloadCount": 999},  # duplicate of ger result — must be dropped
            {"Id": "p/3", "ProviderName": "OpenSubtitles", "Language": "eng",
             "DownloadCount": 200, "IsHashMatch": False},
        ],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        data = responses.get(request.url.path, [])
        return httpx.Response(200, json=data)

    results = await _service_with(handler).search_subtitles("item9", ["ger", "eng"])
    ids = [r.id for r in results]
    # p/2 is a hash match → first; then sorted by download_count desc
    assert ids[0] == "p/2"
    # p/1 kept first occurrence (ger); p/3 added from eng
    assert set(ids) == {"p/1", "p/2", "p/3"}
    assert len(ids) == 3


async def test_search_subtitles_dedupes_input_languages():
    """Duplicate language codes in the input must only trigger one request."""
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(200, json=[])

    await _service_with(handler).search_subtitles("item9", ["ger", "ger", "eng"])
    assert calls.count("/Items/item9/RemoteSearch/Subtitles/ger") == 1
    assert calls.count("/Items/item9/RemoteSearch/Subtitles/eng") == 1


async def test_search_subtitles_tolerates_per_language_error():
    """A failure for one language must not kill results from other languages."""
    def handler(request: httpx.Request) -> httpx.Response:
        if "ger" in request.url.path:
            return httpx.Response(500, json={})
        return httpx.Response(200, json=[
            {"Id": "p/1", "Language": "eng", "DownloadCount": 10},
        ])

    results = await _service_with(handler).search_subtitles("item9", ["ger", "eng"])
    assert len(results) == 1
    assert results[0].id == "p/1"


async def test_search_subtitles_sorts_hash_matches_first():
    """Hash-match entries must come before non-hash entries regardless of language order."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[
            {"Id": "no-hash", "DownloadCount": 999, "IsHashMatch": False},
            {"Id": "is-hash", "DownloadCount": 1, "IsHashMatch": True},
        ])

    results = await _service_with(handler).search_subtitles("item9", ["ger"])
    assert results[0].id == "is-hash"
    assert results[1].id == "no-hash"


# ---------------------------------------------------------------------------
# download_subtitle
# ---------------------------------------------------------------------------

async def test_download_subtitle_url_encodes_id_and_returns_refreshed_tracks():
    """subtitle_id with URL-reserved chars (/) must be percent-encoded in the path.
    After a 204 from Jellyfin the service re-fetches the item and returns the
    updated subtitle track list.
    """
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            # httpx normalises %2F back to / in .path; raw_path preserves encoding
            seen["post_path"] = request.url.raw_path.decode()
            return httpx.Response(204)
        # Re-fetch item after download
        seen["get_path"] = request.url.path
        return httpx.Response(200, json={
            "Id": "item9",
            "Name": "Test",
            "Type": "Movie",
            "MediaSources": [{"Id": "src1", "MediaStreams": [
                {"Index": 3, "Type": "Subtitle", "Codec": "subrip",
                 "Language": "ger", "IsExternal": True, "DisplayTitle": "Deutsch (OpenSubtitles)"},
            ]}],
        })

    tracks = await _service_with(handler).download_subtitle("item9", "opensubtitles/123456")
    # The slash in the id must be encoded as %2F
    assert seen["post_path"] == "/Items/item9/RemoteSearch/Subtitles/opensubtitles%2F123456"
    # After the POST we re-fetch the item to return refreshed tracks
    assert seen["get_path"] == "/Users/u1/Items/item9"
    assert len(tracks) == 1
    assert tracks[0].language == "ger"
    assert tracks[0].is_external is True


async def test_download_subtitle_raises_on_error_status():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(404, json={})
        return httpx.Response(200, json={})

    with pytest.raises(JellyfinError) as exc:
        await _service_with(handler).download_subtitle("item9", "bad/id")
    assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# JellyfinService.shelf()
# ---------------------------------------------------------------------------

async def test_shelf_top_rated_sends_correct_sort_params():
    """sort='top_rated' (default) → sortBy=CommunityRating,SortName, sortOrder=Descending."""
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json={"Items": [{"Id": "m1", "Name": "Top Film", "Type": "Movie"}]})

    items = await _service_with(handler).shelf(sort="top_rated", include_type="Movie")

    assert seen["path"] == "/Items"
    assert seen["params"]["sortBy"] == "CommunityRating,SortName"
    assert seen["params"]["sortOrder"] == "Descending"
    assert seen["params"]["includeItemTypes"] == "Movie"
    assert seen["params"]["recursive"] == "true"
    assert len(items) == 1
    assert items[0].title == "Top Film"


async def test_shelf_random_sends_random_sortby():
    """sort='random' → sortBy=Random, no explicit sortOrder."""
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json={"Items": []})

    await _service_with(handler).shelf(sort="random")

    assert seen["params"]["sortBy"] == "Random"
    assert "sortOrder" not in seen["params"]


async def test_shelf_latest_sends_date_created_sort():
    """sort='latest' → sortBy=DateCreated,SortName, sortOrder=Descending."""
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json={"Items": []})

    await _service_with(handler).shelf(sort="latest")

    assert seen["params"]["sortBy"] == "DateCreated,SortName"
    assert seen["params"]["sortOrder"] == "Descending"


async def test_shelf_unknown_sort_falls_back_to_top_rated():
    """An unrecognised sort value falls back to top_rated behaviour."""
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json={"Items": []})

    await _service_with(handler).shelf(sort="bogus_sort")

    assert seen["params"]["sortBy"] == "CommunityRating,SortName"
    assert seen["params"]["sortOrder"] == "Descending"


async def test_shelf_genres_are_pipe_joined():
    """genres list → genres param joined by '|' for Jellyfin OR-matching."""
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json={"Items": []})

    await _service_with(handler).shelf(genres=["Action", "Komödie"])

    assert seen["params"]["genres"] == "Action|Komödie"


async def test_shelf_no_genres_omits_genres_param():
    """When genres is None or empty, the genres param must not be sent."""
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json={"Items": []})

    await _service_with(handler).shelf(genres=None)
    assert "genres" not in seen["params"]

    await _service_with(handler).shelf(genres=[])
    assert "genres" not in seen["params"]


async def test_shelf_unplayed_adds_filters_param():
    """unplayed=True → filters=IsUnplayed sent to Jellyfin."""
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json={"Items": []})

    await _service_with(handler).shelf(unplayed=True)

    assert seen["params"]["filters"] == "IsUnplayed"


async def test_shelf_played_omits_filters_param():
    """unplayed=False (default) → no filters param."""
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json={"Items": []})

    await _service_with(handler).shelf(unplayed=False)

    assert "filters" not in seen["params"]


async def test_shelf_always_sends_required_params():
    """userId, recursive, imageTypeLimit, fields, startIndex, limit always present."""
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json={"Items": []})

    await _service_with(handler).shelf(limit=8, include_type="Series")

    p = seen["params"]
    assert p["userId"] == "u1"
    assert p["recursive"] == "true"
    assert p["imageTypeLimit"] == "1"
    assert p["startIndex"] == "0"
    assert p["limit"] == "8"
    assert p["includeItemTypes"] == "Series"
    assert "fields" in p  # exact value tested in other assertions


async def test_shelf_defensive_non_dict_response_returns_empty():
    """If Jellyfin returns something other than a dict, shelf returns []."""
    svc = _service_with(lambda r: httpx.Response(200, json=[{"Id": "x", "Name": "Rogue"}]))
    items = await svc.shelf()
    assert items == []


async def test_shelf_maps_items_correctly():
    """Returned items are mapped through map_item just like _items()."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"Items": [
            {"Id": "abc", "Name": "Dune", "Type": "Movie", "ProductionYear": 2021,
             "CommunityRating": 8.0, "ImageTags": {"Primary": "ptag"},
             "UserData": {"Played": False, "PlaybackPositionTicks": 0}},
        ]})

    items = await _service_with(handler).shelf()
    assert len(items) == 1
    assert items[0].id == "abc"
    assert items[0].title == "Dune"
    assert items[0].community_rating == 8.0
