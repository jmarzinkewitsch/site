"""Admin write/config/test endpoints (LAN config UI, unauthenticated by design)."""
from conftest import BEARER


def test_token_returns_existing_bearer(client):
    # The store fixture already seeded a token; ensure_bearer_token returns it as-is.
    r = client.post("/admin/token")
    assert r.status_code == 200
    assert r.json()["bearer_token"] == BEARER


def test_set_config_merges_and_redacts(client):
    r = client.post("/admin/config", json={"tmdb": {"base_url": "http://tmdb", "api_key": "secret-tmdb"}})
    assert r.status_code == 200
    body = r.json()
    assert body["tmdb"]["base_url"] == "http://tmdb"
    assert body["tmdb"]["api_key_set"] is True
    assert body["tmdb"]["configured"] is True
    assert "api_key" not in body["tmdb"]  # never returned in clear
    assert body["tmdb"]["api_key_masked"].endswith("tmdb")


def test_set_config_ignores_unknown_sections(client):
    r = client.post("/admin/config", json={"bogus": {"x": 1}, "tmdb": {"api_key": "k"}})
    assert r.status_code == 200
    assert "bogus" not in r.json()


def test_test_connection_redis_ok(client):
    # InMemoryCache.ping() returns True without touching the network.
    r = client.post("/admin/test/redis")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_test_connection_unconfigured_service_reports_missing(client):
    # TMDB has no key in the fixture → reported as not ok, no network call made.
    r = client.post("/admin/test/tmdb")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert "Key" in body["detail"]


def test_test_connection_unknown_service_is_graceful(client):
    r = client.post("/admin/test/lidarr")
    assert r.status_code == 200
    assert r.json()["ok"] is False
