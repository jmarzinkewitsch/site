from starlette.websockets import WebSocketDisconnect

import deps
from config import ConfigStore
from main import create_app
from models import LibraryItem, StreamInfo


class FakeKioskJellyfin:
    async def continue_watching(self, limit=8):
        return [
            LibraryItem(
                id="m1",
                type="Movie",
                title="Blade Runner",
                year=1982,
                genres=["Sci-Fi"],
                poster_url="http://jf/Items/m1/Images/Primary?api_key=x",
                backdrop_url="http://jf/Items/m1/Images/Backdrop?api_key=x",
                played_percentage=42,
            )
        ]

    async def next_up(self, limit=8):
        return [
            LibraryItem(
                id="e1",
                type="Episode",
                title="Pilot",
                series_name="Severance",
                episode_code="S01E01",
            )
        ]

    async def latest(self, include_type, limit):
        return [LibraryItem(id=f"{include_type}-1", type=include_type, title=f"Latest {include_type}")]

    async def shelf(self, *, include_type="Movie", sort="top_rated", genres=None, unplayed=False, limit=16):
        return [LibraryItem(id="spot-1", type="Movie", title="Spotlight")]

    async def item(self, item_id):
        return LibraryItem(
            id=item_id,
            type="Movie",
            title="Blade Runner",
            overview="Replicants return to Earth.",
            year=1982,
            runtime_seconds=7020,
            poster_url="http://jf/Items/m1/Images/Primary?api_key=x",
            backdrop_url="http://jf/Items/m1/Images/Backdrop?api_key=x",
        )

    async def stream(self, item_id):
        return StreamInfo(url=f"http://jf/Videos/{item_id}/stream?api_key=x", runtime_seconds=7020)


def test_kiosk_shell_is_served(client):
    r = client.get("/kiosk")
    assert r.status_code == 200
    assert "Vault Kiosk" in r.text
    assert "/kiosk/app.js" in r.text


def test_kiosk_status_requires_bearer(client, auth):
    assert client.get("/kiosk/status").status_code == 401

    r = client.get("/kiosk/status", headers=auth)
    assert r.status_code == 200
    assert r.json() == {"ok": True, "mode": "kiosk", "realtime": "/realtime"}


def test_kiosk_session_requires_allowed_device_ip(client, store):
    store.update(kiosk_device={"allowed_ips": ["192.168.0.118"]})
    r = client.post("/kiosk/session")
    assert r.status_code == 403


def test_kiosk_session_issues_scoped_token_for_allowed_ip(client, store):
    store.update(kiosk_device={"allowed_ips": ["testclient"]})

    r = client.post("/kiosk/session")

    assert r.status_code == 200
    token = r.json()["token"]
    assert token
    assert store.get().kiosk_token == token


def test_kiosk_media_overview_accepts_scoped_token(client, store):
    store.update(kiosk_token="kiosk-media-token", jellyfin={"base_url": "http://jf", "api_key": "x", "user_id": "u"})
    fake = FakeKioskJellyfin()
    client.app.dependency_overrides[deps.get_jellyfin] = lambda: fake
    try:
        r = client.get("/kiosk/media/overview", headers={"Authorization": "Bearer kiosk-media-token"})
    finally:
        client.app.dependency_overrides.pop(deps.get_jellyfin, None)

    assert r.status_code == 200
    body = r.json()
    assert body["continue_watching"][0]["title"] == "Blade Runner"
    assert body["continue_watching"][0]["progress"] == 42
    assert body["next_up"][0]["subtitle"] == "Severance · S01E01"
    assert body["spotlight"][0]["title"] == "Spotlight"


def test_kiosk_media_item_returns_scoped_playback_detail(client, store):
    store.update(kiosk_token="kiosk-media-token", jellyfin={"base_url": "http://jf", "api_key": "x", "user_id": "u"})
    fake = FakeKioskJellyfin()
    client.app.dependency_overrides[deps.get_jellyfin] = lambda: fake
    try:
        r = client.get("/kiosk/media/item/m1", headers={"Authorization": "Bearer kiosk-media-token"})
    finally:
        client.app.dependency_overrides.pop(deps.get_jellyfin, None)

    assert r.status_code == 200
    body = r.json()
    assert body["title"] == "Blade Runner"
    assert body["playable"] is True
    # Stream + images go through vault-api's proxy — never the raw Jellyfin URL or key.
    assert body["stream_url"] == "/kiosk/media/stream/m1"
    assert body["poster_url"] == "/kiosk/media/image/m1?kind=primary"
    assert "api_key" not in (body["stream_url"] + (body["poster_url"] or ""))


def test_realtime_rejects_missing_token(client):
    try:
        with client.websocket_connect("/realtime"):
            raise AssertionError("websocket should not connect without token")
    except WebSocketDisconnect as exc:
        assert exc.code == 1008


def test_realtime_accepts_token_and_pongs(client, store):
    client.app.state.config_store = store
    with client.websocket_connect("/realtime?token=test-bearer-token") as ws:
        assert ws.receive_json()["type"] == "hello"
        ws.send_json({"type": "ping"})
        assert ws.receive_json() == {"type": "pong"}


def test_realtime_accepts_scoped_kiosk_token(client, store):
    store.update(kiosk_token="kiosk-socket-token")
    client.app.state.config_store = store
    with client.websocket_connect("/realtime?token=kiosk-socket-token") as ws:
        assert ws.receive_json()["type"] == "hello"


def test_realtime_uses_app_state_config_without_dependency_override(tmp_path):
    store = ConfigStore(tmp_path / "config.json")
    store.update(bearer_token="socket-token")
    app = create_app()

    from fastapi.testclient import TestClient

    with TestClient(app) as bare_client:
        app.state.config_store = store
        with bare_client.websocket_connect("/realtime?token=socket-token") as ws:
            assert ws.receive_json()["type"] == "hello"


class _TrailerJellyfin(FakeKioskJellyfin):
    async def item(self, item_id):
        return LibraryItem(
            id=item_id,
            type="Movie",
            title="Blade Runner",
            trailer_url="https://youtube/watch?v=x",
        )


def test_kiosk_trailer_accepts_scoped_token(client, store, monkeypatch):
    import routers.kiosk as kiosk_router
    from models import TrailerStreamInfo

    store.update(kiosk_token="kiosk-media-token", jellyfin={"base_url": "http://jf", "api_key": "x", "user_id": "u"})
    monkeypatch.setattr(
        kiosk_router,
        "_resolve_trailer_stream",
        lambda url: _async_value(TrailerStreamInfo(url="https://cdn/t.mp4", container="mp4")),
    )
    client.app.dependency_overrides[deps.get_jellyfin] = lambda: _TrailerJellyfin()
    try:
        r = client.get("/kiosk/media/item/m1/trailer", headers={"Authorization": "Bearer kiosk-media-token"})
    finally:
        client.app.dependency_overrides.pop(deps.get_jellyfin, None)

    assert r.status_code == 200
    body = r.json()
    assert body == {"url": "https://cdn/t.mp4", "container": "mp4"}


def test_kiosk_trailer_404_without_trailer(client, store):
    store.update(kiosk_token="kiosk-media-token", jellyfin={"base_url": "http://jf", "api_key": "x", "user_id": "u"})
    client.app.dependency_overrides[deps.get_jellyfin] = lambda: FakeKioskJellyfin()
    try:
        r = client.get("/kiosk/media/item/m1/trailer", headers={"Authorization": "Bearer kiosk-media-token"})
    finally:
        client.app.dependency_overrides.pop(deps.get_jellyfin, None)
    assert r.status_code == 404


async def _async_value(value):
    return value
