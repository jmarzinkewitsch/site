"""Credential and settings store for vault-api.

All foreign keys (Jellyfin, Radarr/Sonarr/Lidarr, TMDB, OMDb, Anthropic) live
here and are fed by the LAN web-config UI (see routers/admin.py) — never by the
tvOS app. Persisted as JSON; secrets stay out of git (see .gitignore).

Empty fields fall back to environment variables so the stack can be bootstrapped
from docker-compose before the web UI is opened.
"""
from __future__ import annotations

import json
import os
import secrets
import threading
from pathlib import Path

from pydantic import BaseModel, Field

CONFIG_PATH = Path(os.environ.get("VAULT_CONFIG_PATH", "config.json"))

# Which env var seeds each empty field on first load (bootstrap convenience).
_ENV_BOOTSTRAP = {
    ("bearer_token",): "VAULT_BEARER_TOKEN",
    ("kiosk_token",): "VAULT_KIOSK_TOKEN",
    ("jellyfin", "base_url"): "JELLYFIN_URL",
    ("jellyfin", "api_key"): "JELLYFIN_TOKEN",
    ("jellyfin", "user_id"): "JELLYFIN_USER_ID",
    ("jellyfin", "device_id"): "JELLYFIN_DEVICE_ID",
    ("roon", "base_url"): "ROON_API_URL",
    ("homeassistant", "base_url"): "HOME_ASSISTANT_URL",
    ("homeassistant", "api_key"): "HOME_ASSISTANT_TOKEN",
    ("immich", "base_url"): "IMMICH_URL",
    ("immich", "api_key"): "IMMICH_TOKEN",
}


class ServiceConfig(BaseModel):
    base_url: str = ""
    api_key: str = ""

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.api_key)


class JellyfinConfig(ServiceConfig):
    # Jellyfin needs a user context for most library endpoints.
    user_id: str = ""
    device_id: str = "vault-api"

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.api_key and self.user_id)


class UrlServiceConfig(BaseModel):
    base_url: str = ""

    @property
    def configured(self) -> bool:
        return bool(self.base_url)


class ArrDefaults(BaseModel):
    """Default Radarr/Sonarr add options chosen once in the admin UI (M4)."""
    quality_profile_id: int | None = None
    root_folder: str | None = None


class KioskSceneConfig(BaseModel):
    id: str
    label: str
    entity_id: str = ""
    service: str = "scene.turn_on"
    active_state: str = ""


class KioskLightRoomConfig(BaseModel):
    id: str
    label: str
    status_entity_ids: list[str] = Field(default_factory=list)
    scenes: list[KioskSceneConfig] = Field(default_factory=list)


class KioskClimateConfig(BaseModel):
    id: str
    label: str
    entity_id: str = ""


class KioskCoffeeConfig(BaseModel):
    label: str = "Kaffeemaschine"
    entity_id: str = "switch.kaffeemaschine"


class KioskWeatherConfig(BaseModel):
    entity_id: str = "weather.wetter_in_hamburg"


class KioskHomeConfig(BaseModel):
    lights: list[KioskLightRoomConfig] = Field(default_factory=list)
    climates: list[KioskClimateConfig] = Field(default_factory=list)
    coffee: KioskCoffeeConfig = Field(default_factory=KioskCoffeeConfig)
    weather: KioskWeatherConfig = Field(default_factory=KioskWeatherConfig)
    window_entities: list[str] = Field(default_factory=list)


class KioskTodayConfig(BaseModel):
    calendar_entities: list[str] = Field(
        default_factory=lambda: [
            "calendar.arbeit",
            "calendar.kalender",
            "calendar.tanno_und_janno",
            "calendar.familie",
            "calendar.privat",
            "calendar.arbeitskalender",
        ]
    )
    todo_entities: list[str] = Field(
        default_factory=lambda: [
            "todo.einkaufsliste",
            "todo.erinnerungen",
            "todo.familie",
        ]
    )
    news_headline_entity: str = "input_text.hamburg_news_headline"
    news_summary_entity: str = "input_text.hamburg_news_summary"


class KioskPodcastFeedConfig(BaseModel):
    id: str
    title: str = ""
    url: str


class KioskPodcastPlayerConfig(BaseModel):
    id: str
    label: str
    entity_id: str
    roon_zone_id: str = ""


class KioskPodcastsConfig(BaseModel):
    feeds: list[KioskPodcastFeedConfig] = Field(default_factory=list)
    players: list[KioskPodcastPlayerConfig] = Field(
        default_factory=lambda: [
            KioskPodcastPlayerConfig(id="wohnzimmer", label="Wohnzimmer", entity_id="media_player.wohnzimmer_3"),
            KioskPodcastPlayerConfig(id="kuche", label="Küche", entity_id="media_player.kuche_3"),
            KioskPodcastPlayerConfig(id="schlafzimmer", label="Schlafzimmer", entity_id="media_player.schlafzimmer_3"),
        ]
    )
    default_player_id: str = "wohnzimmer"
    cache_ttl_seconds: int = 1800


class KioskDeviceConfig(BaseModel):
    allowed_ips: list[str] = Field(default_factory=lambda: ["192.168.0.118"])


class KioskPhotosConfig(BaseModel):
    mode: str = "random"  # random | album | people
    album_id: str = ""
    person_ids: list[str] = Field(default_factory=list)  # mode=people: assets with ALL listed people
    count: int = 24


class CastConfig(BaseModel):
    appletv_entity: str = "media_player.appletv"
    appletv_source: str = "Vault"  # HA source name of the Vault app — verify live


class VaultConfig(BaseModel):
    # The single shared secret the tvOS app sends as `Authorization: Bearer …`.
    bearer_token: str = ""
    # Scoped token for the wall-mounted Kiosk browser.
    kiosk_token: str = ""
    jellyfin: JellyfinConfig = Field(default_factory=JellyfinConfig)
    radarr: ServiceConfig = Field(default_factory=ServiceConfig)
    sonarr: ServiceConfig = Field(default_factory=ServiceConfig)
    lidarr: ServiceConfig = Field(default_factory=ServiceConfig)
    tmdb: ServiceConfig = Field(default_factory=ServiceConfig)
    omdb: ServiceConfig = Field(default_factory=ServiceConfig)
    anthropic: ServiceConfig = Field(default_factory=ServiceConfig)
    roon: UrlServiceConfig = Field(default_factory=UrlServiceConfig)
    homeassistant: ServiceConfig = Field(default_factory=ServiceConfig)
    immich: ServiceConfig = Field(default_factory=ServiceConfig)
    kiosk_home: KioskHomeConfig = Field(default_factory=KioskHomeConfig)
    kiosk_today: KioskTodayConfig = Field(default_factory=KioskTodayConfig)
    kiosk_podcasts: KioskPodcastsConfig = Field(default_factory=KioskPodcastsConfig)
    kiosk_photos: KioskPhotosConfig = Field(default_factory=KioskPhotosConfig)
    kiosk_device: KioskDeviceConfig = Field(default_factory=KioskDeviceConfig)
    cast: CastConfig = Field(default_factory=CastConfig)
    radarr_defaults: ArrDefaults = Field(default_factory=ArrDefaults)
    sonarr_defaults: ArrDefaults = Field(default_factory=ArrDefaults)


def _apply_env_bootstrap(config: VaultConfig) -> VaultConfig:
    """Fill only still-empty fields from environment variables."""
    for path, env_name in _ENV_BOOTSTRAP.items():
        value = os.environ.get(env_name)
        if not value:
            continue
        target: object = config
        for part in path[:-1]:
            target = getattr(target, part)
        if not getattr(target, path[-1]):
            setattr(target, path[-1], value)
    return config


class ConfigStore:
    """Thread-safe JSON-backed config. Reads stay cheap; the web UI writes."""

    def __init__(self, path: Path = CONFIG_PATH) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._config = self._load_from_disk()

    def _load_from_disk(self) -> VaultConfig:
        if self._path.exists():
            try:
                raw = json.loads(self._path.read_text())
                config = VaultConfig.model_validate(raw)
            except (json.JSONDecodeError, ValueError):
                config = VaultConfig()
        else:
            config = VaultConfig()
        return _apply_env_bootstrap(config)

    def get(self) -> VaultConfig:
        with self._lock:
            # Hand out a copy so callers can't mutate shared state in place.
            return self._config.model_copy(deep=True)

    def update(self, **sections: dict) -> VaultConfig:
        """Merge partial section dicts (e.g. jellyfin={"base_url": …}) and save."""
        with self._lock:
            current = self._config.model_dump()
            for key, value in sections.items():
                if isinstance(value, dict) and isinstance(current.get(key), dict):
                    current[key].update(value)
                else:
                    current[key] = value
            self._config = VaultConfig.model_validate(current)
            self._save_locked()
            return self._config.model_copy(deep=True)

    def ensure_bearer_token(self) -> str:
        """Create a bearer token if none exists yet; return the current one."""
        with self._lock:
            if not self._config.bearer_token:
                self._config.bearer_token = secrets.token_urlsafe(24)
                self._save_locked()
            return self._config.bearer_token

    def ensure_kiosk_token(self) -> str:
        """Create a scoped Kiosk token if absent; return the current one."""
        with self._lock:
            if not self._config.kiosk_token:
                self._config.kiosk_token = secrets.token_urlsafe(24)
                self._save_locked()
            return self._config.kiosk_token

    def _save_locked(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.write_text(json.dumps(self._config.model_dump(), indent=2))
        os.replace(tmp, self._path)
        try:
            os.chmod(self._path, 0o600)  # secrets file: owner-only
        except OSError:
            pass


def mask(value: str) -> str:
    """Redact a secret for display: keep nothing but the last 4 chars."""
    if not value:
        return ""
    if len(value) <= 4:
        return "••••"
    return "••••" + value[-4:]
