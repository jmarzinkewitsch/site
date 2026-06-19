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
