"""OMDb client + mapping (M5, optional).

Adds IMDB/Rotten-Tomatoes/Metacritic scores by IMDB id. Optional: only used
when an OMDb key is configured; otherwise the item detail falls back to
Jellyfin's CommunityRating/CriticRating. The mapper is pure and unit-tested.
"""
from __future__ import annotations

import httpx

from config import ServiceConfig
from models import ExternalScores

DEFAULT_BASE_URL = "https://www.omdbapi.com"


class OmdbError(Exception):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _num(value: str | None) -> float | None:
    if not value or value == "N/A":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def map_scores(raw: dict) -> ExternalScores | None:
    if not isinstance(raw, dict) or raw.get("Response") == "False":
        return None
    imdb = _num(raw.get("imdbRating"))
    metascore = _num(raw.get("Metascore"))
    rotten = None
    for rating in raw.get("Ratings", []):
        if rating.get("Source") == "Rotten Tomatoes":
            value = (rating.get("Value") or "").rstrip("%")
            rotten = int(value) if value.isdigit() else None
    if imdb is None and metascore is None and rotten is None:
        return None
    return ExternalScores(
        imdb=imdb,
        rotten_tomatoes=rotten,
        metacritic=int(metascore) if metascore is not None else None,
    )


class OmdbService:
    def __init__(self, cfg: ServiceConfig, client: httpx.AsyncClient) -> None:
        self._key = cfg.api_key
        self._base = (cfg.base_url or DEFAULT_BASE_URL).rstrip("/")
        self._client = client

    async def _get(self, params: dict) -> dict:
        try:
            response = await self._client.get(f"{self._base}/", params={"apikey": self._key, **params})
        except httpx.HTTPError as exc:
            raise OmdbError(f"OMDb nicht erreichbar: {exc}") from exc
        if response.status_code >= 400:
            raise OmdbError(f"OMDb {response.status_code}", response.status_code)
        data = response.json()
        return data if isinstance(data, dict) else {}

    async def scores(self, imdb_id: str) -> ExternalScores | None:
        return map_scores(await self._get({"i": imdb_id}))

    async def ping(self) -> bool:
        data = await self._get({"i": "tt0111161"})  # The Shawshank Redemption
        return data.get("Response") == "True"
