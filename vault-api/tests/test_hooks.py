def test_jellyfin_item_added_webhook_invalidates_library_caches(client, auth):
    client.cache.store["lib:series:0:100"] = {"stale": True}
    client.cache.store["lib:movies:0:100"] = {"stale": True}
    client.cache.store["lib:latest:Movie:16"] = {"stale": True}
    client.cache.store["lib:shelf:top_rated:Movie:16"] = {"stale": True}
    client.cache.store["lib:nextup:12"] = {"stale": True}
    client.cache.store["recommend:12:llm:0"] = {"stale": True}
    client.cache.store["lib:item:m1"] = {"keep": True}

    r = client.post(
        "/hooks/jellyfin",
        headers=auth,
        json={"NotificationType": "ItemAdded", "ItemType": "Movie", "Name": "Fresh"},
    )

    assert r.status_code == 200
    assert r.json() == {"flushed": True, "item": "Fresh", "type": "Movie"}
    assert "lib:series:0:100" not in client.cache.store
    assert "lib:movies:0:100" not in client.cache.store
    assert "lib:latest:Movie:16" not in client.cache.store
    assert "lib:shelf:top_rated:Movie:16" not in client.cache.store
    assert "lib:nextup:12" not in client.cache.store
    assert "recommend:12:llm:0" not in client.cache.store
    assert client.cache.store["lib:item:m1"] == {"keep": True}


def test_jellyfin_webhook_ignores_other_events(client, auth):
    client.cache.store["lib:movies:0:100"] = {"keep": True}

    r = client.post(
        "/hooks/jellyfin",
        headers=auth,
        json={"NotificationType": "PlaybackStart"},
    )

    assert r.status_code == 200
    assert r.json() == {"flushed": False, "event": "PlaybackStart"}
    assert client.cache.store["lib:movies:0:100"] == {"keep": True}
