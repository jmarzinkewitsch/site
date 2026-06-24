from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from config import ServiceConfig
from models import PhotoItem


@dataclass
class ImmichResponse:
    status_code: int
    content: bytes
    media_type: str


class ImmichError(Exception):
    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class ImmichService:
    def __init__(self, config: ServiceConfig, http: httpx.AsyncClient) -> None:
        self.base_url = config.base_url.rstrip("/")
        self.http = http
        self.headers = {"x-api-key": config.api_key, "Accept": "application/json"}

    async def ping(self) -> bool:
        try:
            response = await self.http.get(f"{self.base_url}/api/server/about", headers=self.headers)
            return response.status_code < 400
        except httpx.HTTPError:
            return False

    async def random_assets(self, *, count: int = 24) -> list[PhotoItem]:
        raw = await self._get_json("/api/assets/random", params={"count": str(max(1, min(count, 100)))})
        assets = raw if isinstance(raw, list) else raw.get("assets", []) if isinstance(raw, dict) else []
        return [_photo(asset) for asset in assets if isinstance(asset, dict) and asset.get("id")]

    async def album_assets(self, album_id: str, *, count: int = 24) -> list[PhotoItem]:
        raw = await self._get_json(f"/api/albums/{album_id}")
        assets = raw.get("assets", []) if isinstance(raw, dict) else []
        limit = max(1, min(count, 100))
        return [_photo(asset) for asset in assets[:limit] if isinstance(asset, dict) and asset.get("id")]

    async def image(self, asset_id: str, *, size: str = "preview") -> ImmichResponse:
        try:
            response = await self.http.get(
                f"{self.base_url}/api/assets/{asset_id}/thumbnail",
                headers=self.headers,
                params={"size": size},
            )
        except httpx.HTTPError as exc:
            raise ImmichError(str(exc)) from exc
        if response.status_code >= 400:
            raise ImmichError(f"Immich image failed for {asset_id}: {response.status_code}", status_code=502)
        media_type = response.headers.get("content-type", "image/jpeg").split(";")[0]
        return ImmichResponse(status_code=response.status_code, content=response.content, media_type=media_type)

    async def _get_json(self, path: str, *, params: dict[str, str] | None = None) -> Any:
        try:
            response = await self.http.get(f"{self.base_url}{path}", headers=self.headers, params=params)
        except httpx.HTTPError as exc:
            raise ImmichError(str(exc)) from exc
        if response.status_code >= 400:
            raise ImmichError(f"Immich GET {path} failed: {response.status_code}", status_code=502)
        return response.json()


def _photo(raw: dict[str, Any]) -> PhotoItem:
    exif = raw.get("exifInfo") if isinstance(raw.get("exifInfo"), dict) else {}
    title = raw.get("originalFileName") or raw.get("fileName")
    asset_id = str(raw["id"])
    return PhotoItem(
        id=asset_id,
        title=str(title) if title else None,
        taken_at=raw.get("fileCreatedAt") or raw.get("createdAt") or exif.get("dateTimeOriginal"),
        image_url=f"/photos/image/{asset_id}",
    )
