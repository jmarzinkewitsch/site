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




def test_latest_served_by_type_and_cached(client, auth):
    r = client.get("/library/latest?type=Series&limit=8", headers=auth)
    assert r.status_code == 200
    assert r.json()[0]["title"] == "Freshly Added"
    assert r.json()[0]["type"] == "Series"

    # Second call (same type+limit) must hit the cache, not Jellyfin again.
    client.get("/library/latest?type=Series&limit=8", headers=auth)
    assert client.fake_jellyfin.latest_calls == 1


def test_next_up_served_and_cached(client, auth):
    r = client.get("/library/nextup?limit=12", headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert body[0]["type"] == "Episode"
    assert body[0]["series_name"] == "Severance"
    assert body[0]["episode_code"] == "S1 E2"
    assert body[0]["played_percentage"] == 25
    assert body[0]["backdrop_url"]

    # Second call must hit the short-lived cache, not Jellyfin again.
    client.get("/library/nextup?limit=12", headers=auth)
    assert client.fake_jellyfin.next_up_calls == 1


def test_series_seasons_and_episodes_served_and_cached(client, auth):
    r = client.get("/library/series/s1/seasons", headers=auth)
    assert r.status_code == 200
    assert r.json()[0]["id"] == "season1"
    assert r.json()[0]["series_id"] == "s1"

    # Second call must hit the cache, not Jellyfin again.
    client.get("/library/series/s1/seasons", headers=auth)
    assert client.fake_jellyfin.seasons_calls == 1

    r = client.get("/library/series/s1/seasons/season1/episodes", headers=auth)
    assert r.status_code == 200
    assert r.json()[0]["type"] == "Episode"
    assert r.json()[0]["episode_code"] == "S1 E1"

    client.get("/library/series/s1/seasons/season1/episodes", headers=auth)
    assert client.fake_jellyfin.episodes_calls == 1


def test_item_not_found_maps_to_404(client, auth):
    client.fake_jellyfin.item_error = JellyfinError("missing", status_code=404)
    assert client.get("/library/item/x", headers=auth).status_code == 404


def test_item_upstream_error_maps_to_502(client, auth):
    # A non-client Jellyfin failure is an upstream problem → 502 Bad Gateway.
    client.fake_jellyfin.item_error = JellyfinError("boom", status_code=500)
    assert client.get("/library/item/x", headers=auth).status_code == 502


def test_item_upstream_auth_error_maps_to_502(client, auth):
    # A bad/expired Jellyfin credential surfaces upstream as 401/403. It must
    # NOT be forwarded as 401: the app reserves that for an invalid vault bearer
    # token, so report it as an upstream error instead.
    for code in (401, 403):
        client.fake_jellyfin.item_error = JellyfinError("upstream auth", status_code=code)
        assert client.get("/library/item/x", headers=auth).status_code == 502


def test_list_not_found_preserves_status(client, auth):
    # The list path used to flatten every Jellyfin error to 502; a 404 must survive.
    client.fake_jellyfin.movies_error = JellyfinError("missing", status_code=404)
    assert client.get("/library/movies", headers=auth).status_code == 404


def test_list_upstream_error_maps_to_502(client, auth):
    client.fake_jellyfin.movies_error = JellyfinError("boom")
    assert client.get("/library/movies", headers=auth).status_code == 502


def test_progress_not_found_preserves_status(client, auth):
    client.fake_jellyfin.progress_error = JellyfinError("missing", status_code=404)
    r = client.post("/library/item/x/progress", headers=auth,
                    json={"position_seconds": 1.0, "is_paused": False})
    assert r.status_code == 404


def test_stream_returns_url(client, auth):
    r = client.get("/stream/item42", headers=auth)
    assert r.status_code == 200
    assert "Videos/item42/stream" in r.json()["url"]


def test_progress_reports_and_invalidates_cache(client, auth):
    # Prime caches that a progress write should clear.
    client.cache.store["lib:item:m1"] = {"stale": True}
    client.cache.store["lib:continue"] = [{"stale": True}]
    client.cache.store["lib:nextup:12"] = [{"stale": True}]
    client.cache.store["lib:movies:0:100"] = [{"stale": True}]
    client.cache.store["recommend:12:llm:0"] = {"stale": True}

    r = client.post("/library/item/m1/progress", headers=auth,
                    json={"position_seconds": 42.0, "is_paused": False})
    assert r.status_code == 204
    assert client.fake_jellyfin.progress_calls == [("m1", 42.0, False)]
    assert "lib:item:m1" not in client.cache.store
    assert "lib:continue" not in client.cache.store
    assert "lib:nextup:12" not in client.cache.store
    assert "lib:movies:0:100" not in client.cache.store
    assert "recommend:12:llm:0" not in client.cache.store  # recs depend on watched state


def test_set_rating_writes_and_invalidates(client, auth):
    # user_rating rides in these cached shelves too → all must be dropped.
    client.cache.store["lib:item:m1"] = {"stale": True}
    client.cache.store["lib:continue"] = [{"stale": True}]
    client.cache.store["lib:nextup:12"] = [{"stale": True}]
    client.cache.store["lib:movies:0:100"] = [{"stale": True}]
    client.cache.store["lib:series:0:100"] = [{"stale": True}]
    client.cache.store["recommend:12:llm:0"] = {"stale": True}
    r = client.post("/library/item/m1/rating", headers=auth, json={"rating": 8})
    assert r.status_code == 204
    assert client.fake_jellyfin.ratings == [("m1", 8.0)]
    assert "lib:item:m1" not in client.cache.store
    assert "lib:continue" not in client.cache.store
    assert "lib:nextup:12" not in client.cache.store
    assert "lib:movies:0:100" not in client.cache.store
    assert "lib:series:0:100" not in client.cache.store
    assert "recommend:12:llm:0" not in client.cache.store  # recs depend on rating


def test_set_watched_marks_played_and_invalidates_playback_caches(client, auth):
    client.cache.store["lib:item:m1"] = {"stale": True}
    client.cache.store["lib:continue"] = [{"stale": True}]
    client.cache.store["lib:nextup"] = [{"stale": True}]
    client.cache.store["lib:nextup:12"] = [{"stale": True}]
    client.cache.store["lib:movies:0:100"] = [{"stale": True}]
    client.cache.store["lib:series:0:100"] = [{"stale": True}]
    client.cache.store["lib:series:s1:season:season1:episodes"] = [{"stale": True}]
    client.cache.store["lib:latest:Movie:16"] = [{"stale": True}]
    client.cache.store["recommend:12:llm:0"] = {"stale": True}

    r = client.post("/library/item/m1/watched", headers=auth, json={"watched": True})

    assert r.status_code == 204
    assert client.fake_jellyfin.watched_calls == [("m1", True)]
    assert "lib:item:m1" not in client.cache.store
    assert "lib:continue" not in client.cache.store
    assert "lib:nextup" not in client.cache.store
    assert "lib:nextup:12" not in client.cache.store
    assert "lib:movies:0:100" not in client.cache.store
    assert "lib:series:0:100" not in client.cache.store
    assert "lib:series:s1:season:season1:episodes" not in client.cache.store
    assert "lib:latest:Movie:16" not in client.cache.store
    assert "recommend:12:llm:0" not in client.cache.store


def test_set_watched_false_marks_unplayed(client, auth):
    r = client.post("/library/item/m1/watched", headers=auth, json={"watched": False})
    assert r.status_code == 204
    assert client.fake_jellyfin.watched_calls == [("m1", False)]


def test_set_watched_not_found_preserves_status(client, auth):
    client.fake_jellyfin.watched_error = JellyfinError("missing", status_code=404)
    r = client.post("/library/item/x/watched", headers=auth, json={"watched": True})
    assert r.status_code == 404


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


def test_rating_snapshot_persists_without_jellyfin(client, auth):
    payload = {
        "title": "The Babadook",
        "type": "Movie",
        "year": 2014,
        "tmdb_id": 242224,
        "imdb_id": "tt2321549",
        "janno_rating": 8,
        "tanno_rating": 6.5,
        "tanno_fear_factor": 9,
    }
    r = client.post("/ratings/item/jf-gone/snapshot", headers=auth, json=payload)
    assert r.status_code == 201
    body = r.json()
    assert body["item_id"] == "jf-gone"
    assert body["tmdb_id"] == 242224
    assert body["tanno_fear_factor"] == 9

    # The snapshot is stored in Vault's DB, not Jellyfin, so it remains readable
    # even when the Jellyfin item endpoint would now fail after deletion.
    client.fake_jellyfin.item_error = JellyfinError("missing", status_code=404)
    r = client.get("/ratings/item/jf-gone/snapshot", headers=auth)
    assert r.status_code == 200
    assert r.json()["title"] == "The Babadook"


def test_rating_snapshot_upsert_and_invalidates_recommendations(client, auth):
    client.cache.store["recommend:12:llm:0"] = {"stale": True}
    r = client.post("/ratings/item/m1/snapshot", headers=auth, json={
        "title": "Blade Runner",
        "type": "Movie",
        "janno_rating": 7,
        "tanno_rating": 8,
        "tanno_fear_factor": 2,
    })
    assert r.status_code == 201
    first_updated = r.json()["updated_at"]
    assert "recommend:12:llm:0" not in client.cache.store

    r = client.post("/ratings/item/m1/snapshot", headers=auth, json={
        "title": "Blade Runner Final Cut",
        "type": "Movie",
        "janno_rating": 9,
        "tanno_rating": 8,
        "tanno_fear_factor": 1,
    })
    assert r.status_code == 201
    assert r.json()["title"] == "Blade Runner Final Cut"
    assert r.json()["janno_rating"] == 9
    assert r.json()["updated_at"] >= first_updated

    r = client.get("/ratings/snapshots", headers=auth)
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_rating_snapshot_validates_ranges(client, auth):
    payload = {"title": "Nope", "type": "Movie", "janno_rating": 11}
    assert client.post("/ratings/item/m1/snapshot", headers=auth, json=payload).status_code == 422
    payload = {"title": "Nope", "type": "Movie", "tanno_fear_factor": -1}
    assert client.post("/ratings/item/m1/snapshot", headers=auth, json=payload).status_code == 422
