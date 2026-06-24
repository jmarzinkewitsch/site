from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from auth import require_bearer_or_kiosk
from config import KioskClimateConfig, KioskHomeConfig, KioskLightRoomConfig, KioskSceneConfig, VaultConfig
from deps import get_config, get_homeassistant
from models import (
    HomeClimate,
    HomeClimateUpdate,
    HomeCoffee,
    HomeCoffeeUpdate,
    HomeLightRoom,
    HomeOverview,
    HomeScene,
    HomeWeather,
    HomeWindow,
)
from services.homeassistant import HAState, HomeAssistantError, HomeAssistantService

router = APIRouter(prefix="/home", tags=["home"], dependencies=[Depends(require_bearer_or_kiosk)])


def _ha_error(exc: HomeAssistantError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.message)


def _friendly_name(state: HAState) -> str:
    return str(state.attributes.get("friendly_name") or state.entity_id)


def _state_float(state: HAState | None, key: str) -> float | None:
    if state is None:
        return None
    value = state.attributes.get(key)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _scene_active(scene: KioskSceneConfig, state: HAState | None) -> bool:
    if not scene.active_state or state is None:
        return False
    return state.state == scene.active_state


def _room_light_states(room: KioskLightRoomConfig, states: dict[str, HAState]) -> list[HAState]:
    return [states[entity_id] for entity_id in room.status_entity_ids if entity_id in states]


def _room_state(room: KioskLightRoomConfig, states: dict[str, HAState]) -> str:
    light_states = _room_light_states(room, states)
    if light_states:
        return "an" if any(state.state == "on" for state in light_states) else "aus"
    for scene in room.scenes:
        if _scene_active(scene, states.get(scene.entity_id)):
            return scene.label
    return "unknown"


async def _overview(config: KioskHomeConfig, ha: HomeAssistantService) -> HomeOverview:
    scene_entities = [scene.entity_id for room in config.lights for scene in room.scenes]
    light_status_entities = [entity_id for room in config.lights for entity_id in room.status_entity_ids]
    climate_entities = [climate.entity_id for climate in config.climates]
    entity_ids = (
        scene_entities
        + light_status_entities
        + climate_entities
        + [config.coffee.entity_id, config.weather.entity_id]
        + config.window_entities
    )
    states = await ha.states(entity_ids)

    lights: list[HomeLightRoom] = []
    lights_on = 0
    for room in config.lights:
        room_state = _room_state(room, states)
        lights_on += sum(1 for state in _room_light_states(room, states) if state.state == "on")
        lights.append(
            HomeLightRoom(
                id=room.id,
                label=room.label,
                state=room_state,
                scenes=[
                    HomeScene(
                        id=scene.id,
                        label=scene.label,
                        active=_scene_active(scene, states.get(scene.entity_id)),
                    )
                    for scene in room.scenes
                ],
            )
        )

    climates = [
        HomeClimate(
            id=climate.id,
            label=climate.label,
            entity_id=climate.entity_id,
            current_temperature=_state_float(states.get(climate.entity_id), "current_temperature"),
            target_temperature=_state_float(states.get(climate.entity_id), "temperature"),
            hvac_mode=states.get(climate.entity_id).state if states.get(climate.entity_id) else None,
            preset_mode=(states.get(climate.entity_id).attributes.get("preset_mode") if states.get(climate.entity_id) else None),
        )
        for climate in config.climates
    ]

    coffee_state = states.get(config.coffee.entity_id)
    coffee = HomeCoffee(
        label=config.coffee.label,
        entity_id=config.coffee.entity_id,
        on=coffee_state.state == "on" if coffee_state else False,
        state=coffee_state.state if coffee_state else "unknown",
    )

    weather_state = states.get(config.weather.entity_id)
    weather = HomeWeather(
        entity_id=config.weather.entity_id,
        state=weather_state.state if weather_state else "unknown",
        temperature=_state_float(weather_state, "temperature"),
    )

    windows: list[HomeWindow] = []
    for entity_id in config.window_entities:
        state = states.get(entity_id)
        if state is None:
            windows.append(HomeWindow(entity_id=entity_id, label=entity_id))
            continue
        windows.append(
            HomeWindow(
                entity_id=entity_id,
                label=_friendly_name(state),
                open=state.state == "on",
                state=state.state,
            )
        )

    return HomeOverview(
        lights=lights,
        climates=climates,
        coffee=coffee,
        weather=weather,
        windows=windows,
        lights_on=lights_on,
        windows_open=sum(1 for window in windows if window.open),
    )


def _find_room(config: KioskHomeConfig, room_id: str) -> KioskLightRoomConfig:
    for room in config.lights:
        if room.id == room_id:
            return room
    raise HTTPException(status_code=404, detail="Raum nicht für den Kiosk freigegeben")


def _find_scene(room: KioskLightRoomConfig, scene_id: str) -> KioskSceneConfig:
    for scene in room.scenes:
        if scene.id == scene_id:
            return scene
    raise HTTPException(status_code=404, detail="Szene nicht für den Kiosk freigegeben")


def _find_climate(config: KioskHomeConfig, climate_id: str) -> KioskClimateConfig:
    for climate in config.climates:
        if climate.id == climate_id:
            return climate
    raise HTTPException(status_code=404, detail="Thermostat nicht für den Kiosk freigegeben")


@router.get("/overview", response_model=HomeOverview)
async def overview(
    config: VaultConfig = Depends(get_config),
    ha: HomeAssistantService = Depends(get_homeassistant),
) -> HomeOverview:
    try:
        return await _overview(config.kiosk_home, ha)
    except HomeAssistantError as exc:
        raise _ha_error(exc) from exc


@router.post("/lights/{room_id}/scenes/{scene_id}", status_code=204)
async def activate_scene(
    room_id: str,
    scene_id: str,
    config: VaultConfig = Depends(get_config),
    ha: HomeAssistantService = Depends(get_homeassistant),
) -> None:
    room = _find_room(config.kiosk_home, room_id)
    scene = _find_scene(room, scene_id)
    if not scene.entity_id:
        raise HTTPException(status_code=503, detail="Szene ist nicht konfiguriert")
    try:
        await ha.call_service(scene.service, entity_id=scene.entity_id)
    except HomeAssistantError as exc:
        raise _ha_error(exc) from exc


@router.post("/climate/{climate_id}", response_model=HomeOverview)
async def set_climate(
    climate_id: str,
    body: HomeClimateUpdate,
    config: VaultConfig = Depends(get_config),
    ha: HomeAssistantService = Depends(get_homeassistant),
) -> HomeOverview:
    climate = _find_climate(config.kiosk_home, climate_id)
    if not climate.entity_id:
        raise HTTPException(status_code=503, detail="Thermostat ist nicht konfiguriert")
    data = {}
    if body.target_temperature is not None:
        data["temperature"] = body.target_temperature
    if body.hvac_mode:
        data["hvac_mode"] = body.hvac_mode
    try:
        if data:
            await ha.call_service("climate.set_temperature", entity_id=climate.entity_id, data=data)
        if body.preset_mode:
            await ha.call_service(
                "climate.set_preset_mode",
                entity_id=climate.entity_id,
                data={"preset_mode": body.preset_mode},
            )
        return await _overview(config.kiosk_home, ha)
    except HomeAssistantError as exc:
        raise _ha_error(exc) from exc


@router.post("/coffee", response_model=HomeOverview)
async def set_coffee(
    body: HomeCoffeeUpdate,
    config: VaultConfig = Depends(get_config),
    ha: HomeAssistantService = Depends(get_homeassistant),
) -> HomeOverview:
    entity_id = config.kiosk_home.coffee.entity_id
    if not entity_id:
        raise HTTPException(status_code=503, detail="Kaffeemaschine ist nicht konfiguriert")
    try:
        await ha.call_service("switch.turn_on" if body.on else "switch.turn_off", entity_id=entity_id)
        return await _overview(config.kiosk_home, ha)
    except HomeAssistantError as exc:
        raise _ha_error(exc) from exc
