import json

import deps
from services.roon import RoonError, RoonResponse


class FakeRoon:
    def __init__(self):
        self.calls = []

    async def proxy(self, method, path, *, params=None, json=None):
        self.calls.append((method, path, params, json))
        return RoonResponse(
            status_code=200,
            content=b'{"ok":true}',
            media_type="application/json",
        )


class FailingRoon:
    async def proxy(self, method, path, *, params=None, json=None):
        raise RoonError("Roon nicht erreichbar", status_code=502)


def test_roon_requires_bearer(client):
    assert client.get("/roon/status").status_code == 401


def test_roon_proxy_forwards_get(client, auth):
    fake = FakeRoon()
    client.app.dependency_overrides[deps.get_roon] = lambda: fake
    try:
        r = client.get("/roon/albums?query=blue&limit=24", headers=auth)
    finally:
        client.app.dependency_overrides.pop(deps.get_roon, None)

    assert r.status_code == 200
    assert r.json() == {"ok": True}
    assert fake.calls == [("GET", "albums", {"query": "blue", "limit": "24"}, None)]


def test_roon_proxy_forwards_post_body(client, auth):
    fake = FakeRoon()
    client.app.dependency_overrides[deps.get_roon] = lambda: fake
    payload = {"zoneId": "zone-1", "action": "playpause"}
    try:
        r = client.post("/roon/transport", headers=auth, json=payload)
    finally:
        client.app.dependency_overrides.pop(deps.get_roon, None)

    assert r.status_code == 200
    assert json.loads(r.content) == {"ok": True}
    assert fake.calls == [("POST", "transport", {}, payload)]


def test_roon_proxy_maps_transport_errors(client, auth):
    client.app.dependency_overrides[deps.get_roon] = lambda: FailingRoon()
    try:
        r = client.get("/roon/status", headers=auth)
    finally:
        client.app.dependency_overrides.pop(deps.get_roon, None)

    assert r.status_code == 502
    assert r.json()["detail"] == "Roon nicht erreichbar"
