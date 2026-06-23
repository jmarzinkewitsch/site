"""Tests for the Apple-TV cast feature: HA launch helpers + /cast router."""
from __future__ import annotations

import deps
from services.homeassistant import HAState, HomeAssistantService


class _FakeHTTP:
    def __init__(self):
        self.calls = []

    async def post(self, url, headers=None, json=None, timeout=None):
        self.calls.append((url, json))

        class R:
            status_code = 200

        return R()


async def test_launch_apple_tv_wakes_then_selects_source():
    from config import ServiceConfig

    http = _FakeHTTP()
    svc = HomeAssistantService(ServiceConfig(base_url="http://ha", api_key="k"), http)
    await svc.launch_apple_tv("media_player.appletv", "Vault")
    assert "/api/services/media_player/turn_on" in http.calls[0][0]
    assert "/api/services/media_player/select_source" in http.calls[1][0]
    assert http.calls[1][1] == {"entity_id": "media_player.appletv", "source": "Vault"}


async def test_launch_apple_tv_skips_source_when_none():
    from config import ServiceConfig

    http = _FakeHTTP()
    svc = HomeAssistantService(ServiceConfig(base_url="http://ha", api_key="k"), http)
    await svc.launch_apple_tv("media_player.appletv", None)
    assert len(http.calls) == 1
    assert "/api/services/media_player/turn_on" in http.calls[0][0]


# ---------------------------------------------------------------------------
# Task A2: /cast/appletv router
# ---------------------------------------------------------------------------


class FakeCastHA:
    """Records launch_apple_tv calls; returns a configurable player state."""

    def __init__(self, state: HAState | None = None):
        self.launched: list[tuple[str, str | None]] = []
        self._state = state if state is not None else HAState(
            entity_id="media_player.appletv", state="playing", attributes={"app_name": "Vault"}
        )

    async def launch_apple_tv(self, entity_id, source=None):
        self.launched.append((entity_id, source))

    async def media_player_state(self, entity_id):
        return self._state


def test_cast_post_stores_pending_and_calls_ha(client, store):
    store.update(kiosk_token="kt", homeassistant={"base_url": "http://ha", "api_key": "k"})
    fake = FakeCastHA()
    client.app.dependency_overrides[deps.get_homeassistant] = lambda: fake
    try:
        r = client.post("/cast/appletv", headers={"Authorization": "Bearer kt"}, json={"item_id": "m1"})
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert body["item_id"] == "m1"
        assert body["appletv"] == "playing"
        assert fake.launched == [("media_player.appletv", "Vault")]

        # /pending uses the full bearer token (tvOS only), consume-once.
        p = client.get("/cast/appletv/pending", headers={"Authorization": "Bearer test-bearer-token"})
        assert p.status_code == 200
        assert p.json()["item_id"] == "m1"
        p2 = client.get("/cast/appletv/pending", headers={"Authorization": "Bearer test-bearer-token"})
        assert p2.json()["item_id"] is None
    finally:
        client.app.dependency_overrides.pop(deps.get_homeassistant, None)


def test_cast_pending_requires_full_bearer(client, store):
    # Kiosk-scoped token must NOT be able to read /pending.
    store.update(kiosk_token="kt")
    r = client.get("/cast/appletv/pending", headers={"Authorization": "Bearer kt"})
    assert r.status_code == 401


def test_cast_pending_empty_when_nothing_queued(client):
    r = client.get("/cast/appletv/pending", headers={"Authorization": "Bearer test-bearer-token"})
    assert r.status_code == 200
    assert r.json() == {"item_id": None, "created_at": None}


def test_cast_status_reports_online_state(client, store):
    store.update(kiosk_token="kt", homeassistant={"base_url": "http://ha", "api_key": "k"})
    fake = FakeCastHA(HAState(entity_id="media_player.appletv", state="idle", attributes={"app_name": "Vault"}))
    client.app.dependency_overrides[deps.get_homeassistant] = lambda: fake
    try:
        r = client.get("/cast/appletv/status", headers={"Authorization": "Bearer kt"})
        assert r.status_code == 200
        body = r.json()
        assert body["online"] is True
        assert body["state"] == "idle"
        assert body["app"] == "Vault"
    finally:
        client.app.dependency_overrides.pop(deps.get_homeassistant, None)


def test_cast_status_offline_when_standby(client, store):
    store.update(kiosk_token="kt", homeassistant={"base_url": "http://ha", "api_key": "k"})
    fake = FakeCastHA(HAState(entity_id="media_player.appletv", state="standby", attributes={}))
    client.app.dependency_overrides[deps.get_homeassistant] = lambda: fake
    try:
        r = client.get("/cast/appletv/status", headers={"Authorization": "Bearer kt"})
        assert r.json()["online"] is False
        assert r.json()["app"] is None
    finally:
        client.app.dependency_overrides.pop(deps.get_homeassistant, None)
