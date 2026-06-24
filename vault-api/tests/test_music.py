import deps
from services.roon import RoonResponse


class FakeMusicRoon:
    def __init__(self):
        self.gets = []
        self.posts = []

    async def get_json(self, path, *, params=None):
        self.gets.append((path, params))
        if path == "status":
            return {"connected": True, "core_name": "RoonCloud", "zone_count": 1}
        if path == "zones":
            return {
                "zones": [
                    {
                        "zone_id": "zone-1",
                        "display_name": "Wohnzimmer",
                        "state": "playing",
                        "now_playing": {
                            "title": "Self Control",
                            "subtitle": "Frank Ocean / Blonde",
                            "image_key": "img-1",
                            "seek_position": 42,
                            "length": 301,
                        },
                        "outputs": [
                            {
                                "output_id": "out-1",
                                "display_name": "Wohnzimmer",
                                "volume": {"value": 55},
                                "can_group_with_output_ids": ["out-2"],
                            },
                        ],
                    }
                ]
            }
        if path == "search":
            return {
                "source": params.get("source", "roon"),
                "title": "Search",
                "query": params["query"],
                "results": [
                    {
                        "item_key": "s-1",
                        "title": "Blue Train",
                        "subtitle": "John Coltrane",
                        "image_key": "img-2",
                        "hint": "play",
                        "parent_title": "Albums",
                        "hierarchy": "search",
                        "browser_session_key": "search-1",
                    }
                ],
                "total": 1,
                "offset": int(params.get("offset", 0)),
                "limit": int(params.get("limit", 24)),
                "expanded": True,
            }
        if path == "albums":
            return {
                "albums": [
                    {
                        "item_key": "1:0",
                        "album_index": 0,
                        "title": "Blonde",
                        "subtitle": "Frank Ocean",
                        "image_key": "img-1",
                        "is_playable": True,
                    }
                ],
                "total": 1,
                "offset": 0,
                "limit": 24,
                "query": params.get("query", "") if params else "",
            }
        raise AssertionError(path)

    async def post_json(self, path, *, json=None):
        self.posts.append((path, json))
        return {"ok": True}

    async def image(self, image_key, *, width=500, height=500):
        return RoonResponse(status_code=200, content=b"jpg", media_type="image/jpeg")


def test_music_requires_bearer(client):
    assert client.get("/music/status").status_code == 401


def test_music_accepts_kiosk_token(client, store):
    store.update(kiosk_token="kiosk-music-token", roon={"base_url": "http://roon.local"})
    fake = FakeMusicRoon()
    client.app.dependency_overrides[deps.get_roon] = lambda: fake
    try:
        r = client.get("/music/status", headers={"Authorization": "Bearer kiosk-music-token"})
    finally:
        client.app.dependency_overrides.pop(deps.get_roon, None)

    assert r.status_code == 200
    assert r.json() == {"connected": True, "core_name": "RoonCloud", "zone_count": 1}


def test_music_zones_are_curated(client, auth):
    fake = FakeMusicRoon()
    client.app.dependency_overrides[deps.get_roon] = lambda: fake
    try:
        r = client.get("/music/zones", headers=auth)
    finally:
        client.app.dependency_overrides.pop(deps.get_roon, None)

    assert r.status_code == 200
    body = r.json()
    assert body[0]["id"] == "zone-1"
    assert body[0]["now_playing"]["image_url"] == "/music/image/img-1?width=900&height=900"
    assert body[0]["outputs"][0]["volume"] == 55
    assert body[0]["outputs"][0]["can_group_with_output_ids"] == ["out-2"]


def test_music_albums_maps_cover_urls(client, auth):
    fake = FakeMusicRoon()
    client.app.dependency_overrides[deps.get_roon] = lambda: fake
    try:
        r = client.get("/music/albums?query=blonde&limit=24", headers=auth)
    finally:
        client.app.dependency_overrides.pop(deps.get_roon, None)

    assert r.status_code == 200
    assert fake.gets == [("albums", {"query": "blonde", "offset": "0", "limit": "24"})]
    assert r.json()["albums"][0]["image_url"] == "/music/image/img-1?width=500&height=500"


def test_music_search_maps_roon_browser_session(client, auth):
    fake = FakeMusicRoon()
    client.app.dependency_overrides[deps.get_roon] = lambda: fake
    try:
        r = client.get("/music/search?query=coltrane&source=roon&limit=10", headers=auth)
    finally:
        client.app.dependency_overrides.pop(deps.get_roon, None)

    assert r.status_code == 200
    assert fake.gets == [("search", {"query": "coltrane", "source": "roon", "offset": "0", "limit": "10"})]
    result = r.json()["results"][0]
    assert result["image_url"] == "/music/image/img-2?width=500&height=500"
    assert result["hierarchy"] == "search"
    assert result["browser_session_key"] == "search-1"


def test_music_transport_forwards_curated_body(client, auth):
    fake = FakeMusicRoon()
    client.app.dependency_overrides[deps.get_roon] = lambda: fake
    try:
        r = client.post(
            "/music/transport",
            headers=auth,
            json={"zone_id": "zone-1", "action": "playpause", "output_id": "out-1", "volume": 50},
        )
    finally:
        client.app.dependency_overrides.pop(deps.get_roon, None)

    assert r.status_code == 204
    assert fake.posts == [("transport", {"zoneId": "zone-1", "action": "playpause", "outputId": "out-1", "volume": 50})]


def test_music_group_forwards_output_ids(client, auth):
    fake = FakeMusicRoon()
    client.app.dependency_overrides[deps.get_roon] = lambda: fake
    try:
        r = client.post("/music/group", headers=auth, json={"output_ids": ["out-1", "out-2"]})
    finally:
        client.app.dependency_overrides.pop(deps.get_roon, None)

    assert r.status_code == 204
    assert fake.posts == [("group", {"outputIds": ["out-1", "out-2"]})]


def test_music_ungroup_forwards_output_ids(client, auth):
    fake = FakeMusicRoon()
    client.app.dependency_overrides[deps.get_roon] = lambda: fake
    try:
        r = client.post("/music/ungroup", headers=auth, json={"output_ids": ["out-1"]})
    finally:
        client.app.dependency_overrides.pop(deps.get_roon, None)

    assert r.status_code == 204
    assert fake.posts == [("ungroup", {"outputIds": ["out-1"]})]


def test_music_play_forwards_album_request(client, auth):
    fake = FakeMusicRoon()
    client.app.dependency_overrides[deps.get_roon] = lambda: fake
    try:
        r = client.post(
            "/music/play",
            headers=auth,
            json={"zone_id": "zone-1", "item_key": "1:0", "album_index": 0},
        )
    finally:
        client.app.dependency_overrides.pop(deps.get_roon, None)

    assert r.status_code == 204
    assert fake.posts == [("play", {"zoneId": "zone-1", "itemKey": "1:0", "albumIndex": 0})]


def test_music_image_proxies_bytes(client, auth):
    fake = FakeMusicRoon()
    client.app.dependency_overrides[deps.get_roon] = lambda: fake
    try:
        r = client.get("/music/image/img-1?width=300&height=300", headers=auth)
    finally:
        client.app.dependency_overrides.pop(deps.get_roon, None)

    assert r.status_code == 200
    assert r.content == b"jpg"
    assert r.headers["content-type"] == "image/jpeg"


def test_music_image_accepts_kiosk_token_query(client, store):
    store.update(kiosk_token="kiosk-image-token", roon={"base_url": "http://roon.local"})
    fake = FakeMusicRoon()
    client.app.dependency_overrides[deps.get_roon] = lambda: fake
    try:
        r = client.get("/music/image/img-1?width=300&height=300&token=kiosk-image-token")
    finally:
        client.app.dependency_overrides.pop(deps.get_roon, None)

    assert r.status_code == 200
    assert r.content == b"jpg"
