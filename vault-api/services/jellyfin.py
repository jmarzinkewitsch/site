"""Jellyfin client + DTO mapping.

This is the only place that knows Jellyfin's wire shape. The mapping functions
(`map_item`, `image_url`, `stream_url`, `auth_header`) are pure and unit-tested;
`JellyfinService` adds the async HTTP calls on top.
"""
from __future__ import annotations

import logging

import httpx

from config import JellyfinConfig
from models import AudioTrackInfo, LibraryItem, MediaSegment, StreamInfo

TICKS_PER_SECOND = 10_000_000
PROGRESS_VERIFY_TOLERANCE_TICKS = 10 * TICKS_PER_SECOND
logger = logging.getLogger(__name__)

# Fields we ask Jellyfin to include so a single call has everything the app needs.
# ProviderIds rides along so list responses carry a usable tmdb_id — the
# recommender relies on it to drop already-owned titles from the discover shelf.
_DEFAULT_FIELDS = "Overview,Genres,ProviderIds,PrimaryImageAspectRatio"
_NEXT_UP_FIELDS = "Overview,Genres,ProviderIds,PrimaryImageAspectRatio"
_DETAIL_FIELDS = "Overview,Genres,MediaSources,MediaStreams,PrimaryImageAspectRatio"
_SEARCH_FIELDS = "Overview,Genres,ProviderIds,PrimaryImageAspectRatio"


class JellyfinError(Exception):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def auth_header(cfg: JellyfinConfig) -> str:
    """`Authorization: MediaBrowser Client="Vault", Device=…, Token=…`.

    Mirrors the tvOS client's JellyfinAuthHeader so both identify identically.
    """
    value = (
        'MediaBrowser Client="Vault", Device="vault-api", '
        f'DeviceId="{cfg.device_id}", Version="0.1.0"'
    )
    if cfg.api_key:
        value += f', Token="{cfg.api_key}"'
    return value


def _ticks_to_seconds(ticks: int | None) -> float | None:
    if ticks is None:
        return None
    return ticks / TICKS_PER_SECOND


def _segment_seconds(raw: dict, key: str) -> float | None:
    value = raw.get(key)
    if value is None:
        value = raw.get(key.removesuffix("Ticks"))
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if key.endswith("Ticks") or number > TICKS_PER_SECOND:
        return number / TICKS_PER_SECOND
    return number


def map_media_segments(raw: object) -> list[MediaSegment]:
    items = raw.get("Items", raw.get("MediaSegments", [])) if isinstance(raw, dict) else raw
    if not isinstance(items, list):
        return []
    segments: list[MediaSegment] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        segment_type = str(item.get("Type") or item.get("SegmentType") or "").lower()
        if segment_type not in {"intro", "outro"}:
            continue
        start = _segment_seconds(item, "StartTicks")
        end = _segment_seconds(item, "EndTicks")
        if start is None or end is None or end <= start:
            continue
        segments.append(MediaSegment(type=segment_type, start=start, end=end))
    return segments


def image_url(
    base_url: str,
    item_id: str,
    tag: str,
    image_type: str = "Primary",
    max_width: int | None = None,
    quality: int | None = None,
) -> str:
    base = base_url.rstrip("/")
    url = f"{base}/Items/{item_id}/Images/{image_type}?tag={tag}"
    if max_width is not None:
        url += f"&maxWidth={max_width}"
    if quality is not None:
        url += f"&quality={quality}"
    return url


# Default artwork sizes baked into the URLs so the app fetches constrained
# images instead of original-resolution files. The tvOS client stays
# Jellyfin-agnostic — it just loads whatever URL vault-api hands back.
_POSTER_MAX_WIDTH = 600
_BACKDROP_MAX_WIDTH = 1920
_IMAGE_QUALITY = 90


def stream_url(cfg: JellyfinConfig, item_id: str, media_source_id: str | None = None, audio_stream_index: int | None = None) -> str:
    """Direct-stream URL with api_key in the query.

    In the LAN-first model Jellyfin can't issue signed short URLs, so the token
    rides in the URL — acceptable inside the LAN, and vault-api hands out a
    fresh one per request without caching it.
    """
    base = cfg.base_url.rstrip("/")
    url = f"{base}/Videos/{item_id}/stream?static=true&api_key={cfg.api_key}"
    if media_source_id:
        url += f"&mediaSourceId={media_source_id}"
    if audio_stream_index is not None:
        url += f"&audioStreamIndex={audio_stream_index}"
    return url


def _episode_code(item: dict) -> str | None:
    if item.get("Type") != "Episode":
        return None
    parts = []
    if (season := item.get("ParentIndexNumber")) is not None:
        parts.append(f"S{season}")
    if (episode := item.get("IndexNumber")) is not None:
        parts.append(f"E{episode}")
    return " ".join(parts) or None


def audio_tracks_from_item(item: dict, media_source_id: str | None = None) -> list[AudioTrackInfo]:
    streams = item.get("MediaStreams") or []
    if not streams:
        sources = item.get("MediaSources") or []
        source = None
        if media_source_id:
            source = next((s for s in sources if s.get("Id") == media_source_id), None)
        source = source or (sources[0] if sources else None)
        streams = (source or {}).get("MediaStreams") or []
    tracks: list[AudioTrackInfo] = []
    for stream in streams:
        if stream.get("Type") != "Audio" or stream.get("Index") is None:
            continue
        tracks.append(AudioTrackInfo(
            index=stream["Index"],
            language=stream.get("Language"),
            codec=stream.get("Codec"),
            channels=stream.get("Channels"),
            display_title=stream.get("DisplayTitle"),
        ))
    return tracks


def map_item(item: dict, base_url: str) -> LibraryItem:
    """Pure Jellyfin BaseItemDto → LibraryItem mapping."""
    item_id = item["Id"]
    user_data = item.get("UserData") or {}
    runtime_ticks = item.get("RunTimeTicks")
    if runtime_ticks is None:
        sources = item.get("MediaSources") or []
        if sources:
            runtime_ticks = sources[0].get("RunTimeTicks")

    poster = None
    image_tags = item.get("ImageTags") or {}
    if (primary := image_tags.get("Primary")) is not None:
        poster = image_url(base_url, item_id, primary, "Primary",
                           max_width=_POSTER_MAX_WIDTH, quality=_IMAGE_QUALITY)

    backdrop = None
    backdrop_tags = item.get("BackdropImageTags") or []
    if backdrop_tags:
        backdrop = image_url(base_url, item_id, backdrop_tags[0], "Backdrop",
                             max_width=_BACKDROP_MAX_WIDTH, quality=_IMAGE_QUALITY)

    provider_ids = item.get("ProviderIds") or {}
    tmdb_id = None
    raw_tmdb = provider_ids.get("Tmdb")
    if raw_tmdb is not None:
        try:
            tmdb_id = int(raw_tmdb)
        except (TypeError, ValueError):
            tmdb_id = None
    imdb_id = provider_ids.get("Imdb") or None

    return LibraryItem(
        id=item_id,
        type=item.get("Type") or "Movie",
        title=item.get("Name") or "",
        overview=item.get("Overview"),
        year=item.get("ProductionYear"),
        genres=item.get("Genres") or [],
        runtime_seconds=_ticks_to_seconds(runtime_ticks),
        audio_tracks=audio_tracks_from_item(item),
        community_rating=item.get("CommunityRating"),
        critic_rating=item.get("CriticRating"),
        user_rating=user_data.get("Rating"),
        official_rating=item.get("OfficialRating"),
        poster_url=poster,
        backdrop_url=backdrop,
        played=bool(user_data.get("Played", False)),
        played_percentage=user_data.get("PlayedPercentage"),
        resume_position_seconds=_ticks_to_seconds(user_data.get("PlaybackPositionTicks", 0)) or 0.0,
        series_id=item.get("SeriesId"),
        series_name=item.get("SeriesName"),
        season_id=item.get("SeasonId"),
        index_number=item.get("IndexNumber"),
        parent_index_number=item.get("ParentIndexNumber"),
        episode_code=_episode_code(item),
        tmdb_id=tmdb_id,
        imdb_id=imdb_id,
    )


class JellyfinService:
    def __init__(self, cfg: JellyfinConfig, client: httpx.AsyncClient) -> None:
        self._cfg = cfg
        self._client = client

    @property
    def base_url(self) -> str:
        return self._cfg.base_url.rstrip("/")

    def _headers(self) -> dict[str, str]:
        return {"Authorization": auth_header(self._cfg), "Accept": "application/json"}

    async def _get(self, path: str, params: dict | None = None) -> object:
        try:
            response = await self._client.get(
                f"{self.base_url}/{path.lstrip('/')}",
                params=params,
                headers=self._headers(),
            )
        except httpx.HTTPError as exc:
            raise JellyfinError(f"Jellyfin nicht erreichbar: {exc}") from exc
        if response.status_code >= 400:
            raise JellyfinError(f"Jellyfin {response.status_code}", response.status_code)
        return response.json()

    async def _post(self, path: str, *, params: dict | None = None, json: dict | None = None) -> httpx.Response:
        url = f"{self.base_url}/{path.lstrip('/')}"
        logger.info("Jellyfin POST %s params=%s json=%s", path, params, json)
        try:
            response = await self._client.post(
                url,
                params=params,
                json=json,
                headers=self._headers(),
            )
        except httpx.HTTPError as exc:
            raise JellyfinError(f"Jellyfin POST {path} fehlgeschlagen: {exc}") from exc
        logger.info("Jellyfin POST %s -> %s %s", path, response.status_code, response.text[:500])
        return response

    async def _raw_user_item(self, item_id: str) -> dict:
        raw = await self._get(
            f"Users/{self._cfg.user_id}/Items/{item_id}",
            {"fields": _DETAIL_FIELDS},
        )
        if not isinstance(raw, dict):
            raise JellyfinError("Unerwartete Antwort von Jellyfin")
        return raw

    async def _progress_is_recorded(self, item_id: str, target_ticks: int) -> bool:
        raw = await self._raw_user_item(item_id)
        user_data = raw.get("UserData") or {}
        actual = user_data.get("PlaybackPositionTicks")
        try:
            actual_ticks = int(actual)
        except (TypeError, ValueError):
            actual_ticks = 0
        ok = abs(actual_ticks - target_ticks) <= PROGRESS_VERIFY_TOLERANCE_TICKS
        logger.info(
            "Jellyfin progress verify item=%s target_ticks=%s actual_ticks=%s ok=%s",
            item_id,
            target_ticks,
            actual_ticks,
            ok,
        )
        return ok

    async def ping(self) -> bool:
        info = await self._get("System/Info/Public")
        return isinstance(info, dict)

    async def _items(self, include_type: str, start: int, limit: int) -> list[LibraryItem]:
        result = await self._get(
            "Items",
            {
                "userId": self._cfg.user_id,
                "includeItemTypes": include_type,
                "recursive": "true",
                "sortBy": "SortName",
                "sortOrder": "Ascending",
                "startIndex": start,
                "limit": limit,
                "imageTypeLimit": 1,
                "fields": _DEFAULT_FIELDS,
            },
        )
        items = result.get("Items", []) if isinstance(result, dict) else []
        return [map_item(raw, self.base_url) for raw in items]

    async def movies(self, start: int = 0, limit: int = 100) -> list[LibraryItem]:
        return await self._items("Movie", start, limit)

    async def series(self, start: int = 0, limit: int = 100) -> list[LibraryItem]:
        return await self._items("Series", start, limit)

    async def latest(self, include_type: str, limit: int = 16) -> list[LibraryItem]:
        """Recently added items (date-added order), for the "Neu" shelves.

        Unlike /Items, Jellyfin's /Items/Latest returns a bare array already
        sorted by DateCreated descending.
        """
        result = await self._get(
            f"Users/{self._cfg.user_id}/Items/Latest",
            {
                "includeItemTypes": include_type,
                "limit": limit,
                "fields": _DEFAULT_FIELDS,
            },
        )
        items = result if isinstance(result, list) else []
        return [map_item(raw, self.base_url) for raw in items]

    async def seasons(self, series_id: str) -> list[LibraryItem]:
        result = await self._get(
            f"Shows/{series_id}/Seasons",
            {"userId": self._cfg.user_id, "fields": _DEFAULT_FIELDS},
        )
        items = result.get("Items", []) if isinstance(result, dict) else []
        return [map_item(raw, self.base_url) for raw in items]

    async def episodes(self, series_id: str, season_id: str) -> list[LibraryItem]:
        result = await self._get(
            f"Shows/{series_id}/Episodes",
            {
                "userId": self._cfg.user_id,
                "seasonId": season_id,
                "fields": _DETAIL_FIELDS,
            },
        )
        items = result.get("Items", []) if isinstance(result, dict) else []
        return [map_item(raw, self.base_url) for raw in items]

    async def item(self, item_id: str) -> LibraryItem:
        raw = await self._raw_user_item(item_id)
        return map_item(raw, self.base_url)

    async def continue_watching(self, limit: int = 12) -> list[LibraryItem]:
        result = await self._get(
            f"Users/{self._cfg.user_id}/Items/Resume",
            {"limit": limit, "mediaTypes": "Video", "fields": _DEFAULT_FIELDS},
        )
        items = result.get("Items", []) if isinstance(result, dict) else []
        return [map_item(raw, self.base_url) for raw in items]

    async def next_up(self, limit: int = 24) -> list[LibraryItem]:
        """Episodes Jellyfin considers next for each in-progress show."""
        result = await self._get(
            "Shows/NextUp",
            {
                "userId": self._cfg.user_id,
                "limit": limit,
                "fields": _NEXT_UP_FIELDS,
                "imageTypeLimit": 1,
            },
        )
        items = result.get("Items", []) if isinstance(result, dict) else []
        return [map_item(raw, self.base_url) for raw in items]

    async def search(self, term: str, limit: int = 24) -> list[LibraryItem]:
        result = await self._get(
            f"Users/{self._cfg.user_id}/Items",
            {
                "searchTerm": term,
                "recursive": "true",
                "includeItemTypes": "Movie,Series",
                "limit": limit,
                "fields": _SEARCH_FIELDS,
            },
        )
        items = result.get("Items", []) if isinstance(result, dict) else []
        return [map_item(raw, self.base_url) for raw in items]

    async def report_progress(
        self,
        item_id: str,
        position_seconds: float,
        is_paused: bool,
        media_source_id: str | None = None,
    ) -> None:
        ticks = int(position_seconds * TICKS_PER_SECOND)
        body = {
            "ItemId": item_id,
            "PlaybackPositionTicks": ticks,
            "IsPaused": is_paused,
        }
        if media_source_id:
            body["MediaSourceId"] = media_source_id
        response = await self._post("Sessions/Playing/Progress", json=body)
        # A non-2xx (expired token, missing item) means Jellyfin did NOT record
        # the progress — surface it so the route doesn't 204 and drop caches.
        if response.status_code >= 400 and response.status_code not in {400, 404, 405}:
            raise JellyfinError(f"Jellyfin {response.status_code}", response.status_code)
        if response.status_code < 400 and await self._progress_is_recorded(item_id, ticks):
            return

        # Some Jellyfin installs accept the session progress call but ignore it
        # when no active playback session exists. Updating UserData records the
        # same resume position for the user without depending on an active session.
        response = await self._post(
            f"UserItems/{item_id}/UserData",
            params={"userId": self._cfg.user_id},
            json={"PlaybackPositionTicks": ticks},
        )
        if response.status_code >= 400:
            raise JellyfinError(f"Jellyfin {response.status_code}", response.status_code)
        if not await self._progress_is_recorded(item_id, ticks):
            raise JellyfinError("Jellyfin hat den Fortschritt nicht gespeichert")

    async def mark_played(self, item_id: str) -> None:
        try:
            response = await self._client.post(
                f"{self.base_url}/Users/{self._cfg.user_id}/PlayedItems/{item_id}",
                headers=self._headers(),
            )
        except httpx.HTTPError as exc:
            raise JellyfinError(f"Watched-Status konnte nicht gespeichert werden: {exc}") from exc
        if response.status_code >= 400:
            raise JellyfinError(f"Jellyfin {response.status_code}", response.status_code)

    async def mark_unplayed(self, item_id: str) -> None:
        try:
            response = await self._client.delete(
                f"{self.base_url}/Users/{self._cfg.user_id}/PlayedItems/{item_id}",
                headers=self._headers(),
            )
        except httpx.HTTPError as exc:
            raise JellyfinError(f"Watched-Status konnte nicht gespeichert werden: {exc}") from exc
        if response.status_code >= 400:
            raise JellyfinError(f"Jellyfin {response.status_code}", response.status_code)

    async def set_rating(self, item_id: str, rating: float) -> None:
        """Write the user's 0–10 rating via UpdateItemUserData (Jellyfin 10.9+).

        The canonical route is POST /UserItems/{itemId}/UserData with userId as a
        query param — not the legacy /Users/{userId}/Items/... path.
        """
        try:
            response = await self._client.post(
                f"{self.base_url}/UserItems/{item_id}/UserData",
                params={"userId": self._cfg.user_id},
                json={"Rating": rating},
                headers=self._headers(),
            )
        except httpx.HTTPError as exc:
            raise JellyfinError(f"Bewertung konnte nicht gespeichert werden: {exc}") from exc
        if response.status_code >= 400:
            raise JellyfinError(f"Jellyfin {response.status_code}", response.status_code)

    async def media_segments(self, item_id: str) -> list[MediaSegment]:
        try:
            raw = await self._get(f"MediaSegments/{item_id}")
        except JellyfinError as exc:
            if exc.status_code in {404, 405}:
                return []
            raise
        return map_media_segments(raw)

    async def stream_info(self, item_id: str, media_source_id: str | None = None) -> StreamInfo:
        return StreamInfo(
            url=stream_url(self._cfg, item_id, media_source_id),
            segments=await self.media_segments(item_id),
        )

    async def stream(self, item_id: str, media_source_id: str | None = None, audio_stream_index: int | None = None) -> StreamInfo:
        raw = await self._get(f"Users/{self._cfg.user_id}/Items/{item_id}", {"fields": _DETAIL_FIELDS})
        item = raw if isinstance(raw, dict) else {}
        return StreamInfo(
            url=stream_url(self._cfg, item_id, media_source_id, audio_stream_index),
            runtime_seconds=_ticks_to_seconds(item.get("RunTimeTicks")),
            audio_tracks=audio_tracks_from_item(item, media_source_id),
            segments=await self.media_segments(item_id),
        )
