"""Sonarr v3 client — series lookup (by tvdbId), add+search, queue."""
from __future__ import annotations

from models import RequestResult
from services.arr import ArrClient, ArrError


class SonarrService(ArrClient):
    media_type = "Series"

    async def lookup_tvdb(self, tvdb_id: int) -> dict | None:
        result = await self._request("GET", "series/lookup", params={"term": f"tvdb:{tvdb_id}"})
        if isinstance(result, list) and result:
            return result[0]
        return None

    async def existing_by_tvdb(self, tvdb_id: int) -> dict | None:
        """The library endpoint filtered by tvdbId returns the *stored* series
        (with its real id) — unlike series/lookup, which is a metadata search."""
        result = await self._request("GET", "series", params={"tvdbId": tvdb_id})
        if isinstance(result, list) and result:
            return result[0]
        return None

    async def add(
        self, tvdb_id: int,
        quality_profile_id: int | None = None, root_folder: str | None = None,
        default_profile: int | None = None, default_root: str | None = None,
    ) -> RequestResult:
        # Already in Sonarr? lookup won't tell us reliably, so ask the library.
        if (existing := await self.existing_by_tvdb(tvdb_id)) is not None:
            return RequestResult(ok=True, status="already_exists",
                                 title=existing.get("title", ""), arr_id=existing.get("id"))

        series = await self.lookup_tvdb(tvdb_id)
        if series is None:
            raise ArrError(f"Kein Sonarr-Treffer für tvdb:{tvdb_id}", status_code=404)
        title = series.get("title", "")

        profile, folder = await self._resolve_defaults(
            quality_profile_id, root_folder, default_profile, default_root)
        payload = {
            **series,
            "qualityProfileId": profile,
            "rootFolderPath": folder,
            "monitored": True,
            "addOptions": {"searchForMissingEpisodes": True},
        }
        created = await self._request("POST", "series", json=payload)
        arr_id = created.get("id") if isinstance(created, dict) else None
        return RequestResult(ok=True, status="added", title=title, arr_id=arr_id)
