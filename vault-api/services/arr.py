"""Shared base for the Radarr/Sonarr v3 clients.

Radarr and Sonarr expose near-identical v3 APIs (auth via `X-Api-Key`), so the
HTTP plumbing, default-resolution and queue mapping live here; radarr.py and
sonarr.py only add the bits that differ (lookup term, id field, add payload).
"""
from __future__ import annotations

import httpx

from models import QueueItem


class ArrError(Exception):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class ArrClient:
    media_type = "Movie"  # overridden by subclasses for queue mapping

    def __init__(self, base_url: str, api_key: str, client: httpx.AsyncClient) -> None:
        self._base = base_url.rstrip("/")
        self._key = api_key
        self._client = client

    def _headers(self) -> dict[str, str]:
        return {"X-Api-Key": self._key, "Accept": "application/json"}

    async def _request(self, method: str, path: str, **kwargs) -> object:
        try:
            response = await self._client.request(
                method, f"{self._base}/api/v3/{path.lstrip('/')}",
                headers=self._headers(), **kwargs,
            )
        except httpx.HTTPError as exc:
            raise ArrError(f"{type(self).__name__} nicht erreichbar: {exc}") from exc
        if response.status_code >= 400:
            raise ArrError(f"{type(self).__name__} {response.status_code}", response.status_code)
        if response.status_code == 204 or not response.content:
            return {}
        return response.json()

    async def quality_profiles(self) -> list[dict]:
        result = await self._request("GET", "qualityprofile")
        return result if isinstance(result, list) else []

    async def root_folders(self) -> list[dict]:
        result = await self._request("GET", "rootfolder")
        return result if isinstance(result, list) else []

    async def _resolve_defaults(
        self, quality_profile_id: int | None, root_folder: str | None,
        default_profile: int | None, default_root: str | None,
    ) -> tuple[int, str]:
        """Pick the request's values, else the admin defaults, else the first
        profile/folder the *arr instance offers."""
        profile = quality_profile_id or default_profile
        if profile is None:
            profiles = await self.quality_profiles()
            if not profiles:
                raise ArrError("Kein Quality-Profile konfiguriert")
            profile = profiles[0]["id"]

        folder = root_folder or default_root
        if not folder:
            folders = await self.root_folders()
            if not folders:
                raise ArrError("Kein Root-Folder konfiguriert")
            folder = folders[0]["path"]
        return profile, folder

    async def queue(self) -> list[QueueItem]:
        result = await self._request("GET", "queue", params={"pageSize": 100})
        records = result.get("records", []) if isinstance(result, dict) else []
        items: list[QueueItem] = []
        for record in records:
            size = record.get("size") or 0
            size_left = record.get("sizeleft")
            progress = 1.0 - (size_left / size) if size and size_left is not None else 0.0
            items.append(QueueItem(
                title=record.get("title", ""),
                type=self.media_type,
                progress=round(max(0.0, min(1.0, progress)), 3),
                status=record.get("status"),
                time_left=record.get("timeleft"),
            ))
        return items

    async def ping(self) -> bool:
        await self._request("GET", "system/status")
        return True
