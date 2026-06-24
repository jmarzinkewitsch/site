from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from config import ServiceConfig


class HomeAssistantError(Exception):
    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@dataclass
class HAState:
    entity_id: str
    state: str
    attributes: dict[str, Any]


class HomeAssistantService:
    def __init__(self, config: ServiceConfig, http: httpx.AsyncClient) -> None:
        self.base_url = config.base_url.rstrip("/")
        self.http = http
        self.headers = {
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
        }

    async def ping(self) -> bool:
        try:
            response = await self.http.get(f"{self.base_url}/api/", headers=self.headers)
            return response.status_code < 500
        except httpx.HTTPError:
            return False

    async def get_json(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> Any:
        clean_path = path if path.startswith("/") else f"/{path}"
        try:
            response = await self.http.get(
                f"{self.base_url}{clean_path}",
                headers=self.headers,
                params=params,
                timeout=timeout if timeout is not None else httpx.USE_CLIENT_DEFAULT,
            )
        except httpx.HTTPError as exc:
            raise HomeAssistantError(str(exc)) from exc
        if response.status_code >= 400:
            raise HomeAssistantError(
                f"Home Assistant GET {clean_path} failed: {response.status_code}",
                status_code=502,
            )
        return response.json()

    async def state(self, entity_id: str) -> HAState | None:
        if not entity_id:
            return None
        try:
            response = await self.http.get(
                f"{self.base_url}/api/states/{entity_id}",
                headers=self.headers,
            )
        except httpx.HTTPError as exc:
            raise HomeAssistantError(str(exc)) from exc
        if response.status_code == 404:
            return None
        if response.status_code >= 400:
            raise HomeAssistantError(
                f"Home Assistant state failed for {entity_id}: {response.status_code}",
                status_code=502,
            )
        raw = response.json()
        return HAState(
            entity_id=raw.get("entity_id", entity_id),
            state=str(raw.get("state", "unknown")),
            attributes=dict(raw.get("attributes") or {}),
        )

    async def states(self, entity_ids: list[str]) -> dict[str, HAState]:
        result: dict[str, HAState] = {}
        for entity_id in dict.fromkeys(e for e in entity_ids if e):
            state = await self.state(entity_id)
            if state is not None:
                result[entity_id] = state
        return result

    async def calendar_events(
        self, entity_id: str, *, start: str, end: str, timeout: float | None = None
    ) -> list[dict[str, Any]]:
        raw = await self.get_json(
            f"/api/calendars/{entity_id}",
            params={"start": start, "end": end},
            timeout=timeout,
        )
        return raw if isinstance(raw, list) else []

    async def todo_items(
        self, entity_id: str, *, status: str = "needs_action", timeout: float | None = None
    ) -> list[dict[str, Any]]:
        try:
            response = await self.http.post(
                f"{self.base_url}/api/services/todo/get_items?return_response",
                headers=self.headers,
                json={"entity_id": entity_id, "status": status},
                timeout=timeout if timeout is not None else httpx.USE_CLIENT_DEFAULT,
            )
        except httpx.HTTPError as exc:
            raise HomeAssistantError(str(exc)) from exc
        if response.status_code >= 400:
            raise HomeAssistantError(
                f"Home Assistant todo.get_items failed for {entity_id}: {response.status_code}",
                status_code=502,
            )
        raw = response.json()
        service_response = raw.get("service_response") if isinstance(raw, dict) else {}
        entity_response = (service_response or {}).get(entity_id, {})
        items = entity_response.get("items", []) if isinstance(entity_response, dict) else []
        return items if isinstance(items, list) else []

    async def launch_apple_tv(self, entity_id: str, source: str | None = None) -> None:
        """Wake the Apple TV and (optionally) switch to the Vault app source."""
        await self.call_service("media_player.turn_on", entity_id=entity_id)
        if source:
            await self.call_service(
                "media_player.select_source", entity_id=entity_id, data={"source": source}
            )

    async def media_player_state(self, entity_id: str) -> HAState | None:
        return await self.state(entity_id)

    async def update_todo_item(self, entity_id: str, *, item: str, status: str) -> None:
        await self.call_service("todo.update_item", entity_id=entity_id, data={"item": item, "status": status})

    async def play_media(
        self,
        entity_id: str,
        *,
        media_content_id: str,
        media_content_type: str = "music",
        enqueue: str | None = None,
    ) -> None:
        data: dict[str, Any] = {
            "media_content_id": media_content_id,
            "media_content_type": media_content_type,
        }
        if enqueue:
            data["enqueue"] = enqueue
        await self.call_service("media_player.play_media", entity_id=entity_id, data=data)

    async def media_player_transport(self, entity_id: str, action: str) -> None:
        service = {
            "play": "media_player.media_play",
            "pause": "media_player.media_pause",
            "playpause": "media_player.media_play_pause",
            "stop": "media_player.media_stop",
            "next": "media_player.media_next_track",
            "previous": "media_player.media_previous_track",
        }.get(action)
        if not service:
            raise HomeAssistantError(f"Ungültige Medienaktion: {action}", status_code=422)
        await self.call_service(service, entity_id=entity_id)

    async def media_seek(self, entity_id: str, position_seconds: float) -> None:
        await self.call_service(
            "media_player.media_seek",
            entity_id=entity_id,
            data={"seek_position": max(0, position_seconds)},
        )

    async def call_service(
        self,
        service: str,
        *,
        entity_id: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        domain, _, service_name = service.partition(".")
        if not domain or not service_name:
            raise HomeAssistantError(f"Ungültiger HA-Service: {service}", status_code=500)
        # HA's REST API takes the service data flat in the body (entity_id +
        # extra fields). The {"target": …, "data": …} split is WebSocket-only and
        # is silently ignored here — it would return 200 but control nothing.
        payload: dict[str, Any] = {"entity_id": entity_id, **(data or {})}
        try:
            response = await self.http.post(
                f"{self.base_url}/api/services/{domain}/{service_name}",
                headers=self.headers,
                json=payload,
            )
        except httpx.HTTPError as exc:
            raise HomeAssistantError(str(exc)) from exc
        if response.status_code >= 400:
            raise HomeAssistantError(
                f"Home Assistant service {service} failed for {entity_id}: {response.status_code}",
                status_code=502,
            )
