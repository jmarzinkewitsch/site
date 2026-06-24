from services.immich import ImmichService
from config import ServiceConfig


class FakeResponse:
    def __init__(self, status_code=200):
        self.status_code = status_code


class FakeHttp:
    def __init__(self):
        self.gets = []

    async def get(self, url, headers=None, params=None):
        self.gets.append((url, headers, params))
        return FakeResponse()


async def test_immich_ping_uses_permissionless_ping_endpoint():
    http = FakeHttp()
    service = ImmichService(ServiceConfig(base_url="http://immich.local", api_key="secret"), http)

    assert await service.ping() is True
    assert http.gets == [
        (
            "http://immich.local/api/server/ping",
            {"x-api-key": "secret", "Accept": "application/json"},
            None,
        )
    ]
