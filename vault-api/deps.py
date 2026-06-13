"""Shared FastAPI dependencies.

Kept in one module so routers stay import-cycle free: they pull state off
`request.app.state`, which main.py populates at startup. Overriding
`get_jellyfin` / `require_bearer` makes the routers trivially testable.
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request

from cache import Cache
from config import ConfigStore, VaultConfig
from services.jellyfin import JellyfinService


def get_store(request: Request) -> ConfigStore:
    return request.app.state.config_store


def get_cache(request: Request) -> Cache:
    return request.app.state.cache


def get_config(store: ConfigStore = Depends(get_store)) -> VaultConfig:
    return store.get()


def get_http(request: Request):
    return request.app.state.http


def get_jellyfin(
    request: Request,
    config: VaultConfig = Depends(get_config),
) -> JellyfinService:
    if not config.jellyfin.configured:
        raise HTTPException(status_code=503, detail="Jellyfin ist nicht konfiguriert")
    return JellyfinService(config.jellyfin, request.app.state.http)
