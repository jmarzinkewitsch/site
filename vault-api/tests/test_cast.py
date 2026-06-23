"""Tests for the Apple-TV cast feature: HA launch helpers + /cast router."""
from __future__ import annotations

from services.homeassistant import HomeAssistantService


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
