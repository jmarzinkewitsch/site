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
from routers import admin, discover, health, library, request, search, stream


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.config_store = ConfigStore()
    app.state.http = httpx.AsyncClient(timeout=15.0)
    app.state.cache = Cache(os.environ.get("REDIS_URL"))
    await app.state.cache.connect()
    try:
        yield
    finally:
        await app.state.http.aclose()
        await app.state.cache.close()


def create_app() -> FastAPI:
    app = FastAPI(title="vault-api", version="0.1.0", lifespan=lifespan)
    app.include_router(health.router)
    app.include_router(library.router)
    app.include_router(stream.router)
    app.include_router(discover.router)
    app.include_router(search.router)
    app.include_router(request.router)
    app.include_router(admin.router)
    return app


app = create_app()
