"""Radarr v3 client — movie lookup, add+search, queue."""
from __future__ import annotations

from models import RequestResult
from services.arr import ArrClient, ArrError


class RadarrService(ArrClient):
    media_type = "Movie"

    async def lookup_tmdb(self, tmdb_id: int) -> dict | None:
        result = await self._request("GET", "movie/lookup", params={"term": f"tmdb:{tmdb_id}"})
        if isinstance(result, list) and result:
            return result[0]
        return None

    async def existing_by_tmdb(self, tmdb_id: int) -> dict | None:
        """The library endpoint filtered by tmdbId returns the *stored* movie
        (with its real id) — unlike movie/lookup, which is a metadata search."""
        result = await self._request("GET", "movie", params={"tmdbId": tmdb_id})
        if isinstance(result, list) and result:
            return result[0]
        return None

    async def add(
        self, tmdb_id: int,
        quality_profile_id: int | None = None, root_folder: str | None = None,
        default_profile: int | None = None, default_root: str | None = None,
    ) -> RequestResult:
        # Already in Radarr? lookup won't tell us reliably, so ask the library.
        if (existing := await self.existing_by_tmdb(tmdb_id)) is not None:
            return RequestResult(ok=True, status="already_exists",
                                 title=existing.get("title", ""), arr_id=existing.get("id"))

        movie = await self.lookup_tmdb(tmdb_id)
        if movie is None:
            raise ArrError(f"Kein Radarr-Treffer für tmdb:{tmdb_id}", status_code=404)
        title = movie.get("title", "")

        profile, folder = await self._resolve_defaults(
            quality_profile_id, root_folder, default_profile, default_root)
        payload = {
            **movie,
            "qualityProfileId": profile,
            "rootFolderPath": folder,
            "monitored": True,
            "addOptions": {"searchForMovie": True},
        }
        created = await self._request("POST", "movie", json=payload)
        arr_id = created.get("id") if isinstance(created, dict) else None
        return RequestResult(ok=True, status="added", title=title, arr_id=arr_id)
