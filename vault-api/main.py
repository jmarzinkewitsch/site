"""vault-api — the single endpoint the Vault tvOS app talks to.

Orchestrates Jellyfin (and, from M4 on, Radarr/Sonarr/TMDB/…) behind one
bearer-authenticated API plus a LAN web-config UI. See docs/architecture-api-first.md.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from cache import Cache
from config import ConfigStore
from services.podcast_store import PodcastStore
from services.profile_store import ProfileStore
from services.rating_store import RatingStore
from routers import admin, cast, discover, health, home, hooks, idle, kiosk, library, music, photos, podcasts, profiles, ratings, recommend, request, roon, search, stream, today


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.config_store = ConfigStore()
    app.state.http = httpx.AsyncClient(timeout=15.0)
    app.state.cache = Cache(os.environ.get("REDIS_URL"))
    app.state.rating_store = RatingStore()
    app.state.podcast_store = PodcastStore()
    app.state.profile_store = ProfileStore()
    # Short-lived in-memory cast command, consumed once by the tvOS Vault app.
    app.state.cast_pending = None
    await app.state.cache.connect()
    try:
        yield
    finally:
        await app.state.http.aclose()
        await app.state.cache.close()


def create_app() -> FastAPI:
    app = FastAPI(title="vault-api", version="0.1.0", lifespan=lifespan)
    app.include_router(health.router)
    app.include_router(home.router)
    app.include_router(today.router)
    app.include_router(music.router)
    app.include_router(podcasts.router)
    app.include_router(photos.router)
    app.include_router(hooks.router)
    app.include_router(library.router)
    app.include_router(stream.router)
    app.include_router(discover.router)
    app.include_router(search.router)
    app.include_router(recommend.router)
    app.include_router(request.router)
    app.include_router(ratings.router)
    app.include_router(roon.router)
    app.include_router(profiles.router)
    app.include_router(kiosk.router)
    app.include_router(idle.router)
    app.include_router(cast.router)
    app.include_router(admin.router)
    return app


app = create_app()
