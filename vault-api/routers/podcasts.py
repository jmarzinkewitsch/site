from __future__ import annotations

import asyncio
import hashlib

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status

from auth import require_bearer_or_kiosk
from config import ConfigStore, KioskPodcastFeedConfig, KioskPodcastsConfig, VaultConfig
from deps import get_cache, get_config, get_homeassistant, get_http, get_optional_roon, get_podcast_store, get_store
from models import (
    PodcastEpisode,
    PodcastFeed,
    PodcastNowPlaying,
    PodcastOverview,
    PodcastPlayRequest,
    PodcastProgressUpdate,
    PodcastPlayer,
    PodcastSearchResponse,
    PodcastSubscribeRequest,
    PodcastTransportUpdate,
)
from services.homeassistant import HomeAssistantError, HomeAssistantService
from services.podcast_store import PodcastStore
from services.podcasts import PodcastError, dump_parsed, fetch_podcast_feed, load_parsed
from services.roon import RoonError, RoonService

router = APIRouter(prefix="/podcasts", tags=["podcasts"], dependencies=[Depends(require_bearer_or_kiosk)])

_SOURCE_TIMEOUT = 12.0
_ITUNES_SEARCH_URL = "https://itunes.apple.com/search"


def _ha_error(exc: HomeAssistantError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.message)


def _podcast_error(exc: PodcastError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.message)


def _roon_error(exc: RoonError) -> HTTPException:
    status_code = exc.status_code if exc.status_code in {400, 404, 503} else 502
    return HTTPException(status_code=status_code, detail=exc.message)


def _players(config: KioskPodcastsConfig) -> list[PodcastPlayer]:
    return [PodcastPlayer(id=player.id, label=player.label, entity_id=player.entity_id) for player in config.players]


def _player(config: KioskPodcastsConfig, player_id: str | None):
    resolved = player_id or config.default_player_id
    player = next((item for item in config.players if item.id == resolved), None)
    if player is None:
        raise HTTPException(status_code=404, detail="Podcast-Player nicht für den Kiosk freigegeben")
    return player


def _feed_id_from_url(url: str) -> str:
    digest = hashlib.sha1(url.strip().lower().encode("utf-8")).hexdigest()[:12]
    return f"pod-{digest}"


def _merge_progress(episodes: list[PodcastEpisode], store: PodcastStore) -> list[PodcastEpisode]:
    progress = store.get_many([episode.id for episode in episodes])
    return [
        episode.model_copy(
            update={
                "resume_seconds": item.position_seconds,
                "completed": item.completed,
            }
        )
        if (item := progress.get(episode.id)) is not None
        else episode
        for episode in episodes
    ]


async def _feed(
    feed_id: str,
    config: KioskPodcastsConfig,
    http: httpx.AsyncClient,
    cache,
):
    feed_config = next((feed for feed in config.feeds if feed.id == feed_id), None)
    if feed_config is None:
        raise HTTPException(status_code=404, detail="Podcast-Feed nicht für den Kiosk freigegeben")
    cache_key = f"kiosk:podcasts:feed:{feed_config.id}"
    cached = await cache.get_json(cache_key)
    if cached:
        return load_parsed(cached)
    parsed = await fetch_podcast_feed(http, feed_config, timeout=_SOURCE_TIMEOUT)
    await cache.set_json(cache_key, dump_parsed(parsed), max(60, config.cache_ttl_seconds))
    return parsed


async def _overview(
    config: KioskPodcastsConfig,
    http: httpx.AsyncClient,
    cache,
    store: PodcastStore,
) -> PodcastOverview:
    results = await asyncio.gather(
        *(_feed(feed.id, config, http, cache) for feed in config.feeds),
        return_exceptions=True,
    )
    feeds: list[PodcastFeed] = []
    episodes: list[PodcastEpisode] = []
    for result in results:
        if isinstance(result, Exception):
            continue
        feeds.append(result.feed)
        episodes.extend(result.episodes[:12])
    episodes.sort(key=lambda episode: episode.published or "", reverse=True)
    episodes = _merge_progress(episodes[:36], store)
    return PodcastOverview(
        feeds=feeds,
        episodes=episodes,
        players=_players(config),
        default_player_id=config.default_player_id,
    )


async def _nowplaying(config: KioskPodcastsConfig, ha: HomeAssistantService) -> list[PodcastNowPlaying]:
    states = await ha.states([player.entity_id for player in config.players])
    items: list[PodcastNowPlaying] = []
    for player in config.players:
        state = states.get(player.entity_id)
        attrs = state.attributes if state else {}
        items.append(
            PodcastNowPlaying(
                player_id=player.id,
                player_label=player.label,
                entity_id=player.entity_id,
                state=state.state if state else "unknown",
                title=attrs.get("media_title"),
                artist=attrs.get("media_artist"),
                album=attrs.get("media_album_name") or attrs.get("media_album_artist"),
                image_url=attrs.get("entity_picture"),
                position=attrs.get("media_position"),
                duration=attrs.get("media_duration"),
            )
        )
    return items


@router.get("/overview", response_model=PodcastOverview)
async def overview(
    config: VaultConfig = Depends(get_config),
    http: httpx.AsyncClient = Depends(get_http),
    store: PodcastStore = Depends(get_podcast_store),
    cache=Depends(get_cache),
) -> PodcastOverview:
    try:
        return await _overview(config.kiosk_podcasts, http, cache, store)
    except PodcastError as exc:
        raise _podcast_error(exc) from exc


@router.get("/search", response_model=PodcastSearchResponse)
async def search(
    q: str,
    http: httpx.AsyncClient = Depends(get_http),
) -> PodcastSearchResponse:
    if not q.strip():
        return PodcastSearchResponse()
    try:
        response = await http.get(
            _ITUNES_SEARCH_URL,
            params={"media": "podcast", "term": q, "limit": 12},
            timeout=_SOURCE_TIMEOUT,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Podcast-Suche ist nicht erreichbar") from exc
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"Podcast-Suche antwortet mit {response.status_code}")
    results = []
    for item in response.json().get("results", []):
        title = item.get("collectionName")
        feed_url = item.get("feedUrl")
        if not title or not feed_url:
            continue
        results.append(
            {
                "title": title,
                "feed_url": feed_url,
                "image_url": item.get("artworkUrl600") or item.get("artworkUrl100"),
                "author": item.get("artistName"),
            }
        )
    return PodcastSearchResponse(results=results)


@router.post("/subscribe", response_model=KioskPodcastFeedConfig, status_code=status.HTTP_201_CREATED)
async def subscribe(
    body: PodcastSubscribeRequest,
    store: ConfigStore = Depends(get_store),
) -> KioskPodcastFeedConfig:
    feed_url = body.feed_url.strip()
    if not feed_url:
        raise HTTPException(status_code=422, detail="feed_url fehlt")
    config = store.get()
    existing = next((feed for feed in config.kiosk_podcasts.feeds if feed.url == feed_url), None)
    if existing is not None:
        return existing
    feed = KioskPodcastFeedConfig(
        id=_feed_id_from_url(feed_url),
        title=(body.title or "").strip(),
        url=feed_url,
    )
    next_config = config.kiosk_podcasts.model_copy(
        update={"feeds": [*config.kiosk_podcasts.feeds, feed]}
    )
    store.update(kiosk_podcasts=next_config.model_dump())
    return feed


@router.get("/nowplaying", response_model=list[PodcastNowPlaying])
async def nowplaying(
    config: VaultConfig = Depends(get_config),
    ha: HomeAssistantService = Depends(get_homeassistant),
) -> list[PodcastNowPlaying]:
    try:
        return await _nowplaying(config.kiosk_podcasts, ha)
    except HomeAssistantError as exc:
        raise _ha_error(exc) from exc


@router.get("/feed/{feed_id}/episodes", response_model=list[PodcastEpisode])
async def feed_episodes(
    feed_id: str,
    config: VaultConfig = Depends(get_config),
    http: httpx.AsyncClient = Depends(get_http),
    store: PodcastStore = Depends(get_podcast_store),
    cache=Depends(get_cache),
) -> list[PodcastEpisode]:
    try:
        parsed = await _feed(feed_id, config.kiosk_podcasts, http, cache)
    except PodcastError as exc:
        raise _podcast_error(exc) from exc
    return _merge_progress(parsed.episodes, store)


@router.post("/progress", status_code=204)
async def progress(
    body: PodcastProgressUpdate,
    store: PodcastStore = Depends(get_podcast_store),
) -> None:
    store.upsert(
        episode_id=body.episode_id,
        position_seconds=body.position_seconds,
        completed=body.completed,
    )


@router.post("/play", status_code=204)
async def play(
    body: PodcastPlayRequest,
    request: Request,
    config: VaultConfig = Depends(get_config),
    ha: HomeAssistantService = Depends(get_homeassistant),
    roon: RoonService | None = Depends(get_optional_roon),
    http: httpx.AsyncClient = Depends(get_http),
    store: PodcastStore = Depends(get_podcast_store),
    cache=Depends(get_cache),
) -> None:
    player = _player(config.kiosk_podcasts, body.player_id)

    try:
        overview_data = await _overview(config.kiosk_podcasts, http, cache, store)
    except PodcastError as exc:
        raise _podcast_error(exc) from exc
    episode = next((item for item in overview_data.episodes if item.id == body.episode_id), None)
    if episode is None:
        raise HTTPException(status_code=404, detail="Podcast-Episode nicht gefunden")

    try:
        if player.roon_zone_id:
            if roon is None:
                raise HTTPException(status_code=503, detail="Roon ist für diesen Podcast-Player nicht konfiguriert")
            await roon.post_json("transport", json={"zoneId": player.roon_zone_id, "action": "pause"})
        await ha.play_media(
            player.entity_id,
            media_content_id=episode.audio_url,
            media_content_type="music",
        )
        if episode.resume_seconds:
            await ha.media_seek(player.entity_id, episode.resume_seconds)
    except RoonError as exc:
        raise _roon_error(exc) from exc
    except HomeAssistantError as exc:
        raise _ha_error(exc) from exc


@router.post("/transport", status_code=204)
async def transport(
    body: PodcastTransportUpdate,
    config: VaultConfig = Depends(get_config),
    ha: HomeAssistantService = Depends(get_homeassistant),
) -> None:
    player = _player(config.kiosk_podcasts, body.player_id)
    try:
        if body.action == "seek_relative":
            if body.seconds is None:
                raise HTTPException(status_code=422, detail="seconds fehlt für seek_relative")
            state = await ha.state(player.entity_id)
            position = (state.attributes if state else {}).get("media_position") or 0
            await ha.media_seek(player.entity_id, max(0, float(position) + body.seconds))
            return
        if body.action == "speed":
            if body.speed is None:
                raise HTTPException(status_code=422, detail="speed fehlt für Tempo")
            try:
                await ha.music_assistant_set_speed(player.entity_id, body.speed)
            except Exception:
                # Music Assistant exposes speed control only for some players.
                # Unsupported targets must not break the kiosk transport surface.
                pass
            return
        await ha.media_player_transport(player.entity_id, body.action)
    except HomeAssistantError as exc:
        raise _ha_error(exc) from exc
