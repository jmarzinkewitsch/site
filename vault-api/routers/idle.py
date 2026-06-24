"""Idle-Board Aggregator — Paket A3.

GET /kiosk/idle/overview  (Auth: require_bearer_or_kiosk)

Bundles weather, film/series, news headlines, photos and now-playing into a
single JSON response.  Every source is fetched concurrently and tolerated
individually: if one raises, the corresponding field becomes null/[] —
the endpoint never returns 5xx due to a downstream failure.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, Depends

from auth import require_bearer_or_kiosk
from config import VaultConfig
from deps import get_config, get_homeassistant, get_http, get_jellyfin, get_optional_roon
from models import (
    IdleForecast,
    IdleMediaCard,
    IdleNowPlaying,
    IdleOverview,
    IdleWeather,
    LibraryItem,
    NewsHeadline,
)
from services.homeassistant import HomeAssistantService
from services.immich import ImmichService
from services.jellyfin import JellyfinService
from services.news import fetch_headlines
from services.roon import RoonService

router = APIRouter(tags=["idle"])

_TZ = ZoneInfo("Europe/Berlin")
_SOURCE_TIMEOUT = 8.0
_FORECAST_COUNT = 4


# ---------------------------------------------------------------------------
# Weather
# ---------------------------------------------------------------------------

def _forecast_label(raw_datetime: str, *, is_hourly: bool) -> str:
    """Return a compact German label: '18 Uhr' for hourly, 'Mi' for daily."""
    try:
        dt = datetime.fromisoformat(raw_datetime).astimezone(_TZ)
    except (ValueError, TypeError):
        return raw_datetime
    if is_hourly:
        return f"{dt.hour} Uhr"
    return dt.strftime("%a")  # Mon, Di, Mi …


async def _get_weather(ha: HomeAssistantService, entity_id: str) -> IdleWeather | None:
    if not entity_id:
        return None
    try:
        state = await ha.state(entity_id)
    except Exception:
        return None

    # Fetch hourly first, fall back to daily if hourly not available
    try:
        hourly_raw = await ha.weather_forecasts(entity_id, forecast_type="hourly", timeout=_SOURCE_TIMEOUT)
    except Exception:
        hourly_raw = []

    try:
        daily_raw = await ha.weather_forecasts(entity_id, forecast_type="daily", timeout=_SOURCE_TIMEOUT)
    except Exception:
        daily_raw = []

    # Build compact forecast list from hourly, padded with daily if needed
    forecast: list[IdleForecast] = []
    for raw in hourly_raw[:_FORECAST_COUNT]:
        dt_str = str(raw.get("datetime") or "")
        cond = raw.get("condition")
        temp = raw.get("temperature")
        if not dt_str or cond is None or temp is None:
            continue
        forecast.append(IdleForecast(
            when=_forecast_label(dt_str, is_hourly=True),
            condition=str(cond),
            temperature=float(temp),
        ))

    # If we don't have enough hourly entries, append daily entries
    for raw in daily_raw:
        if len(forecast) >= _FORECAST_COUNT:
            break
        dt_str = str(raw.get("datetime") or "")
        cond = raw.get("condition")
        temp = raw.get("temperature")
        if not dt_str or cond is None or temp is None:
            continue
        forecast.append(IdleForecast(
            when=_forecast_label(dt_str, is_hourly=False),
            condition=str(cond),
            temperature=float(temp),
        ))

    temp_val: float | None = None
    if state:
        try:
            raw_temp = state.attributes.get("temperature")
            temp_val = float(raw_temp) if raw_temp is not None else None
        except (TypeError, ValueError):
            pass

    return IdleWeather(
        temperature=temp_val,
        condition=state.state if state else "unknown",
        forecast=forecast,
    )


# ---------------------------------------------------------------------------
# Film / Series
# ---------------------------------------------------------------------------

def _media_subtitle(item: LibraryItem) -> str | None:
    if item.type == "Episode":
        bits = [item.series_name, item.episode_code]
        return " · ".join(b for b in bits if b)
    bits = [
        str(item.year) if item.year else None,
        ", ".join(item.genres[:2]) if item.genres else None,
    ]
    return " · ".join(b for b in bits if b) or None


async def _get_film(jellyfin: JellyfinService) -> IdleMediaCard | None:
    try:
        items = await jellyfin.latest("Movie", 8)
    except Exception:
        return None
    item = next((i for i in items if i.backdrop_url), None) or (items[0] if items else None)
    if item is None:
        return None
    return IdleMediaCard(
        id=item.id,
        title=item.title,
        subtitle=_media_subtitle(item),
        reason=None,
        backdrop_url=f"/kiosk/media/image/{item.id}?kind=backdrop" if item.backdrop_url else None,
        type="Movie",
    )


async def _get_series(jellyfin: JellyfinService) -> IdleMediaCard | None:
    try:
        items = await jellyfin.latest("Series", 8)
    except Exception:
        return None
    # Deduplicate by series_id: only the first occurrence per series
    seen_series: set[str] = set()
    for item in items:
        key = item.series_id or item.id
        if key in seen_series:
            continue
        seen_series.add(key)
        return IdleMediaCard(
            id=item.id,
            title=item.title,
            subtitle=_media_subtitle(item),
            reason=None,
            backdrop_url=f"/kiosk/media/image/{item.id}?kind=backdrop" if item.backdrop_url else None,
            type="Series",
        )
    return None


# ---------------------------------------------------------------------------
# Photos
# ---------------------------------------------------------------------------

async def _get_photos(config: VaultConfig, http: httpx.AsyncClient) -> list[str]:
    if not config.immich.configured:
        return []
    svc = ImmichService(config.immich, http)
    cfg = config.kiosk_photos
    try:
        if cfg.mode == "people" and cfg.person_ids:
            photos = await svc.people_assets(cfg.person_ids, count=cfg.count)
        elif cfg.mode == "album" and cfg.album_id:
            photos = await svc.album_assets(cfg.album_id, count=cfg.count)
        elif cfg.album_id:
            photos = await svc.album_assets(cfg.album_id, count=cfg.count)
        else:
            photos = await svc.random_assets(count=cfg.count)
        if not photos and cfg.mode != "random":
            photos = await svc.random_assets(count=cfg.count)
    except Exception:
        return []
    return [photo.image_url for photo in photos]


# ---------------------------------------------------------------------------
# Now Playing
# ---------------------------------------------------------------------------

async def _get_now_playing(
    roon: RoonService | None,
    ha: HomeAssistantService,
    config: VaultConfig,
) -> IdleNowPlaying | None:
    # 1. Try Roon first
    if roon is not None:
        try:
            data = await roon.get_json("zones")
            zones = data.get("zones", []) if isinstance(data, dict) else []
            for zone in zones:
                if zone.get("state") != "playing":
                    continue
                np = zone.get("now_playing")
                if not np:
                    continue
                three_line = np.get("three_line") or {}
                title = three_line.get("line1") or np.get("title")
                subtitle = three_line.get("line2")
                image_key = np.get("image_key")
                return IdleNowPlaying(
                    kind="music",
                    title=title,
                    subtitle=subtitle,
                    image_url=f"/music/image/{image_key}" if image_key else None,
                    position=np.get("seek_position"),
                    duration=np.get("length"),
                )
        except Exception:
            pass

    # 2. Fall back to HA podcast players
    try:
        players = config.kiosk_podcasts.players
        if not players:
            return None
        entity_ids = [p.entity_id for p in players]
        states = await ha.states(entity_ids)
        for player in players:
            state = states.get(player.entity_id)
            if state is None or state.state != "playing":
                continue
            attrs = state.attributes
            return IdleNowPlaying(
                kind="podcast",
                title=attrs.get("media_title"),
                subtitle=attrs.get("media_artist"),
                image_url=attrs.get("entity_picture"),
                position=attrs.get("media_position"),
                duration=attrs.get("media_duration"),
            )
    except Exception:
        pass

    return None


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.get(
    "/kiosk/idle/overview",
    response_model=IdleOverview,
    dependencies=[Depends(require_bearer_or_kiosk)],
)
async def idle_overview(
    config: VaultConfig = Depends(get_config),
    ha: HomeAssistantService = Depends(get_homeassistant),
    jellyfin: JellyfinService = Depends(get_jellyfin),
    http: httpx.AsyncClient = Depends(get_http),
    roon: RoonService | None = Depends(get_optional_roon),
) -> IdleOverview:
    weather_entity_id = config.kiosk_home.weather.entity_id

    # Fetch all sources concurrently; exceptions are captured per-source
    results = await asyncio.gather(
        _get_weather(ha, weather_entity_id),
        _get_film(jellyfin),
        _get_series(jellyfin),
        fetch_headlines(http, config.kiosk_news.feeds, per_feed=config.kiosk_news.per_feed),
        _get_photos(config, http),
        _get_now_playing(roon, ha, config),
        return_exceptions=True,
    )

    def _ok(value, default):
        return default if isinstance(value, BaseException) else value

    weather: IdleWeather | None = _ok(results[0], None)
    film: IdleMediaCard | None = _ok(results[1], None)
    series: IdleMediaCard | None = _ok(results[2], None)
    headlines: list[NewsHeadline] = _ok(results[3], [])
    photos: list[str] = _ok(results[4], [])
    now_playing: IdleNowPlaying | None = _ok(results[5], None)

    return IdleOverview(
        weather=weather,
        film=film,
        series=series,
        headlines=headlines,
        photos=photos,
        now_playing=now_playing,
    )
