"""Shared FastAPI dependencies.

Kept in one module so routers stay import-cycle free: they pull state off
`request.app.state`, which main.py populates at startup. Overriding
`get_jellyfin` / `require_bearer` makes the routers trivially testable.
"""
from __future__ import annotations

import httpx
from fastapi import Depends, HTTPException, Request

from cache import Cache
from config import ConfigStore, VaultConfig
from services.jellyfin import JellyfinService
from services.homeassistant import HomeAssistantService
from services.podcast_store import PodcastStore
from services.profile_store import ProfileStore
from services.rating_store import RatingStore
from services.radarr import RadarrService
from services.roon import RoonService
from services.sonarr import SonarrService
from services.tmdb import TmdbService


def get_store(request: Request) -> ConfigStore:
    return request.app.state.config_store


def get_cache(request: Request) -> Cache:
    return request.app.state.cache


def get_config(store: ConfigStore = Depends(get_store)) -> VaultConfig:
    return store.get()


def get_http(request: Request) -> httpx.AsyncClient:
    return request.app.state.http


def get_rating_store(request: Request) -> RatingStore:
    return request.app.state.rating_store


def get_podcast_store(request: Request) -> PodcastStore:
    return request.app.state.podcast_store


def get_jellyfin(
    request: Request,
    config: VaultConfig = Depends(get_config),
) -> JellyfinService:
    if not config.jellyfin.configured:
        raise HTTPException(status_code=503, detail="Jellyfin ist nicht konfiguriert")
    return JellyfinService(config.jellyfin, request.app.state.http)


def get_tmdb(
    request: Request,
    config: VaultConfig = Depends(get_config),
) -> TmdbService:
    # TMDB's base_url is optional (defaults to the public API), so only the key matters.
    if not config.tmdb.api_key:
        raise HTTPException(status_code=503, detail="TMDB ist nicht konfiguriert")
    return TmdbService(config.tmdb, request.app.state.http)


def get_radarr(
    request: Request,
    config: VaultConfig = Depends(get_config),
) -> RadarrService:
    if not config.radarr.configured:
        raise HTTPException(status_code=503, detail="Radarr ist nicht konfiguriert")
    return RadarrService(config.radarr.base_url, config.radarr.api_key, request.app.state.http)


def get_sonarr(
    request: Request,
    config: VaultConfig = Depends(get_config),
) -> SonarrService:
    if not config.sonarr.configured:
        raise HTTPException(status_code=503, detail="Sonarr ist nicht konfiguriert")
    return SonarrService(config.sonarr.base_url, config.sonarr.api_key, request.app.state.http)


def get_roon(
    request: Request,
    config: VaultConfig = Depends(get_config),
) -> RoonService:
    if not config.roon.configured:
        raise HTTPException(status_code=503, detail="Roon ist nicht konfiguriert")
    return RoonService(config.roon, request.app.state.http)


def get_optional_roon(
    request: Request,
    config: VaultConfig = Depends(get_config),
) -> RoonService | None:
    if not config.roon.configured:
        return None
    return RoonService(config.roon, request.app.state.http)


def get_homeassistant(
    request: Request,
    config: VaultConfig = Depends(get_config),
) -> HomeAssistantService:
    if not config.homeassistant.configured:
        raise HTTPException(status_code=503, detail="Home Assistant ist nicht konfiguriert")
    return HomeAssistantService(config.homeassistant, request.app.state.http)


def get_profile_store(request: Request) -> ProfileStore:
    return request.app.state.profile_store
