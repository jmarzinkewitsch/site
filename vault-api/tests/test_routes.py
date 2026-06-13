from services.jellyfin import JellyfinError


def test_health_unauthenticated_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    names = {s["name"] for s in body["services"]}
    assert "jellyfin" in names and "redis" in names


def test_library_requires_bearer(client):
    assert client.get("/library/movies").status_code == 401


def test_library_rejects_wrong_token(client):
    r = client.get("/library/movies", headers={"Authorization": "Bearer nope"})
    assert r.status_code == 401


def test_movies_served_and_then_cached(client, auth):
    r = client.get("/library/movies", headers=auth)
    assert r.status_code == 200
    assert r.json()[0]["title"] == "Blade Runner"
    # Second call must hit the cache, not Jellyfin again.
    client.get("/library/movies", headers=auth)
    assert client.fake_jellyfin.movies_calls == 1


def test_item_not_found_maps_to_404(client, auth):
    client.fake_jellyfin.item_error = JellyfinError("missing", status_code=404)
    assert client.get("/library/item/x", headers=auth).status_code == 404


def test_stream_returns_url(client, auth):
    r = client.get("/stream/item42", headers=auth)
    assert r.status_code == 200
    assert "Videos/item42/stream" in r.json()["url"]


def test_progress_reports_and_invalidates_cache(client, auth):
    # Prime caches that a progress write should clear.
    client.cache.store["lib:item:m1"] = {"stale": True}
    client.cache.store["lib:continue"] = [{"stale": True}]
    client.cache.store["lib:movies:0:100"] = [{"stale": True}]

    r = client.post("/library/item/m1/progress", headers=auth,
                    json={"position_seconds": 42.0, "is_paused": False})
    assert r.status_code == 204
    assert client.fake_jellyfin.progress_calls == [("m1", 42.0, False)]
    assert "lib:item:m1" not in client.cache.store
    assert "lib:continue" not in client.cache.store
    assert "lib:movies:0:100" not in client.cache.store


def test_set_rating_writes_and_invalidates(client, auth):
    # user_rating rides in these cached shelves too → all must be dropped.
    client.cache.store["lib:item:m1"] = {"stale": True}
    client.cache.store["lib:continue"] = [{"stale": True}]
    client.cache.store["lib:movies:0:100"] = [{"stale": True}]
    client.cache.store["lib:series:0:100"] = [{"stale": True}]
    r = client.post("/library/item/m1/rating", headers=auth, json={"rating": 8})
    assert r.status_code == 204
    assert client.fake_jellyfin.ratings == [("m1", 8.0)]
    assert "lib:item:m1" not in client.cache.store
    assert "lib:continue" not in client.cache.store
    assert "lib:movies:0:100" not in client.cache.store
    assert "lib:series:0:100" not in client.cache.store


def test_set_rating_out_of_range_is_422(client, auth):
    assert client.post("/library/item/m1/rating", headers=auth, json={"rating": 11}).status_code == 422
    assert client.post("/library/item/m1/rating", headers=auth, json={"rating": -1}).status_code == 422


def test_admin_config_is_redacted(client):
    # The store fixture seeded a Jellyfin key; confirm it never returns in clear.
    r = client.get("/admin/config")
    assert r.status_code == 200
    body = r.json()
    assert body["jellyfin"]["api_key_set"] is True
    assert "api_key" not in body["jellyfin"]  # only masked form is exposed
    assert body["jellyfin"]["base_url"] == "http://jf.local"


def test_admin_page_renders(client):
    r = client.get("/admin")
    assert r.status_code == 200
    assert "vault-api" in r.text
