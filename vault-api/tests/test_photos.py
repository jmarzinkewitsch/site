import deps


class FakeResponse:
    def __init__(self, payload=None, content=b"", status_code=200, content_type="application/json"):
        self._payload = payload
        self.content = content
        self.status_code = status_code
        self.headers = {"content-type": content_type}

    def json(self):
        return self._payload


class FakeImmichHttp:
    def __init__(self):
        self.gets = []

    async def get(self, url, headers=None, params=None):
        self.gets.append((url, headers, params))
        if url.endswith("/api/assets/random"):
            return FakeResponse(
                [
                    {
                        "id": "asset-1",
                        "originalFileName": "Kitchen.jpg",
                        "fileCreatedAt": "2026-06-24T10:00:00Z",
                    }
                ]
            )
        if url.endswith("/api/albums/album-1"):
            return FakeResponse(
                {
                    "assets": [
                        {
                            "id": "asset-2",
                            "originalFileName": "Album.jpg",
                            "createdAt": "2026-06-23T18:00:00Z",
                        }
                    ]
                }
            )
        if url.endswith("/api/assets/asset-1/thumbnail"):
            return FakeResponse(content=b"jpg", content_type="image/jpeg")
        raise AssertionError(url)


def test_photos_overview_unconfigured_is_empty(client, auth):
    r = client.get("/photos/overview", headers=auth)
    assert r.status_code == 200
    assert r.json() == {"photos": []}


def test_photos_overview_uses_random_assets(client, store, auth):
    store.update(immich={"base_url": "http://immich.local", "api_key": "k"})
    fake = FakeImmichHttp()
    client.app.dependency_overrides[deps.get_http] = lambda: fake
    try:
        r = client.get("/photos/overview", headers=auth)
    finally:
        client.app.dependency_overrides.pop(deps.get_http, None)

    assert r.status_code == 200
    body = r.json()
    assert body["photos"][0]["id"] == "asset-1"
    assert body["photos"][0]["image_url"] == "/photos/image/asset-1"
    assert fake.gets[0][0] == "http://immich.local/api/assets/random"
    assert fake.gets[0][1]["x-api-key"] == "k"


def test_photos_overview_uses_configured_album(client, store, auth):
    store.update(
        immich={"base_url": "http://immich.local", "api_key": "k"},
        kiosk_photos={"album_id": "album-1", "count": 12},
    )
    fake = FakeImmichHttp()
    client.app.dependency_overrides[deps.get_http] = lambda: fake
    try:
        r = client.get("/photos/overview", headers=auth)
    finally:
        client.app.dependency_overrides.pop(deps.get_http, None)

    assert r.status_code == 200
    assert r.json()["photos"][0]["id"] == "asset-2"
    assert fake.gets[0][0] == "http://immich.local/api/albums/album-1"


def test_photos_image_proxies_bytes_and_accepts_kiosk_query_token(client, store):
    store.update(kiosk_token="photo-token", immich={"base_url": "http://immich.local", "api_key": "k"})
    fake = FakeImmichHttp()
    client.app.dependency_overrides[deps.get_http] = lambda: fake
    try:
        r = client.get("/photos/image/asset-1?token=photo-token")
    finally:
        client.app.dependency_overrides.pop(deps.get_http, None)

    assert r.status_code == 200
    assert r.content == b"jpg"
    assert r.headers["content-type"] == "image/jpeg"
    assert r.headers["cache-control"] == "public, max-age=86400"
    assert fake.gets[0][2] == {"size": "preview"}


class FakePeopleImmichHttp(FakeImmichHttp):
    def __init__(self):
        super().__init__()
        self.posts = []

    async def post(self, url, headers=None, json=None):
        self.posts.append((url, json))
        if url.endswith("/api/search/metadata"):
            return FakeResponse({"assets": {"items": [
                {"id": "both-1", "originalFileName": "Beide.jpg", "fileCreatedAt": "2026-06-24T12:00:00Z"},
            ]}})
        raise AssertionError(url)


def test_photos_overview_people_mode_filters_by_all_person_ids(client, store, auth):
    store.update(
        immich={"base_url": "http://immich.local", "api_key": "k"},
        kiosk_photos={"mode": "people", "person_ids": ["tanni", "jan"], "count": 24},
    )
    fake = FakePeopleImmichHttp()
    client.app.dependency_overrides[deps.get_http] = lambda: fake
    try:
        r = client.get("/photos/overview", headers=auth)
    finally:
        client.app.dependency_overrides.pop(deps.get_http, None)

    assert r.status_code == 200
    assert r.json()["photos"][0]["id"] == "both-1"
    url, body = fake.posts[0]
    assert url == "http://immich.local/api/search/metadata"
    assert body["personIds"] == ["tanni", "jan"]
    assert body["type"] == "IMAGE"
