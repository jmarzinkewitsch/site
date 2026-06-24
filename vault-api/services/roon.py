from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from config import UrlServiceConfig


@dataclass
class RoonResponse:
    status_code: int
    content: bytes
    media_type: str


class RoonError(Exception):
    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class RoonService:
    def __init__(self, config: UrlServiceConfig, http: httpx.AsyncClient) -> None:
        self.base_url = config.base_url.rstrip("/")
        self.http = http

    async def ping(self) -> bool:
        try:
            response = await self.http.get(f"{self.base_url}/api/status")
            return response.status_code < 500
        except httpx.HTTPError:
            return False

    async def proxy(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any = None,
    ) -> RoonResponse:
        clean_path = path.strip("/")
        url = f"{self.base_url}/api/{clean_path}" if clean_path else f"{self.base_url}/api"
        try:
            response = await self.http.request(method, url, params=params, json=json)
        except httpx.HTTPError as exc:
            raise RoonError(str(exc)) from exc

        media_type = response.headers.get("content-type", "application/json").split(";")[0]
        return RoonResponse(
            status_code=response.status_code,
            content=response.content,
            media_type=media_type,
        )

    async def get_json(self, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        response = await self.proxy("GET", path, params=params)
        if response.status_code >= 400:
            raise RoonError(response.content.decode(errors="replace"), status_code=response.status_code)
        return json_loads(response.content)

    async def post_json(self, path: str, *, json: dict[str, Any] | None = None) -> dict[str, Any]:
        response = await self.proxy("POST", path, json=json or {})
        if response.status_code >= 400:
            raise RoonError(response.content.decode(errors="replace"), status_code=response.status_code)
        return json_loads(response.content)

    async def image(self, image_key: str, *, width: int = 500, height: int = 500) -> RoonResponse:
        return await self.proxy(
            "GET",
            f"image/{image_key}",
            params={"width": str(width), "height": str(height)},
        )


def json_loads(content: bytes) -> dict[str, Any]:
    import json

    raw = json.loads(content.decode("utf-8"))
    return raw if isinstance(raw, dict) else {}
