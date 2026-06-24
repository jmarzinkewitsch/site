from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, Depends, HTTPException

from auth import require_bearer_or_kiosk
from config import VaultConfig
from deps import get_config, get_homeassistant
from models import (
    TodayEvent,
    TodayNews,
    TodayOverview,
    TodayTodoItem,
    TodayTodoList,
    TodayTodoUpdate,
    TodayWeather,
    TodayWeatherForecast,
)
from services.homeassistant import HAState, HomeAssistantError, HomeAssistantService

router = APIRouter(prefix="/today", tags=["today"], dependencies=[Depends(require_bearer_or_kiosk)])


def _ha_error(exc: HomeAssistantError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.message)


def _friendly_name(state: HAState | None, fallback: str) -> str:
    if state is None:
        return fallback
    return str(state.attributes.get("friendly_name") or fallback)


def _event_time(raw: dict, key: str) -> tuple[str, bool]:
    value = raw.get(key)
    if isinstance(value, dict):
        if value.get("dateTime"):
            return str(value["dateTime"]), False
        if value.get("date"):
            return str(value["date"]), True
    return str(value or ""), False


def _todo_item(raw: dict) -> TodayTodoItem:
    return TodayTodoItem(
        uid=raw.get("uid"),
        summary=str(raw.get("summary") or ""),
        status=str(raw.get("status") or "needs_action"),
        description=raw.get("description"),
        due=raw.get("due"),
    )


def _float_value(raw: dict, key: str) -> float | None:
    value = raw.get(key)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _weather_forecast(raw: dict) -> TodayWeatherForecast | None:
    datetime_value = str(raw.get("datetime") or "")
    if not datetime_value:
        return None
    condition = raw.get("condition")
    return TodayWeatherForecast(
        datetime=datetime_value,
        condition=str(condition) if condition is not None else None,
        temperature=_float_value(raw, "temperature"),
        templow=_float_value(raw, "templow"),
        precipitation_probability=_float_value(raw, "precipitation_probability"),
        precipitation=_float_value(raw, "precipitation"),
        wind_speed=_float_value(raw, "wind_speed"),
    )


# Per-source timeout so one slow HA calendar/todo backend can't stall — or 502 —
# the whole Heute page. Each source is fetched concurrently and failures are
# tolerated: a broken calendar just drops out instead of killing the overview.
_SOURCE_TIMEOUT = 8.0
_CALENDAR_LOOKAHEAD_DAYS = 90
_HOURLY_FORECAST_LIMIT = 8
_DAILY_FORECAST_LIMIT = 5


async def _calendar_events(
    ha: HomeAssistantService, entity_id: str, label: str, start: str, end: str
) -> list[TodayEvent]:
    try:
        raw_events = await ha.calendar_events(entity_id, start=start, end=end, timeout=_SOURCE_TIMEOUT)
    except (HomeAssistantError, httpx.HTTPError):
        return []
    events: list[TodayEvent] = []
    for raw in raw_events:
        start_value, start_all_day = _event_time(raw, "start")
        end_value, end_all_day = _event_time(raw, "end")
        events.append(
            TodayEvent(
                calendar_id=entity_id,
                calendar_label=label,
                summary=str(raw.get("summary") or raw.get("message") or "Termin"),
                start=start_value,
                end=end_value or None,
                all_day=start_all_day or end_all_day,
                location=raw.get("location"),
            )
        )
    return events


async def _todo_list(ha: HomeAssistantService, entity_id: str, label: str) -> TodayTodoList:
    try:
        raw_items = await ha.todo_items(entity_id, status="needs_action", timeout=_SOURCE_TIMEOUT)
    except (HomeAssistantError, httpx.HTTPError):
        raw_items = []
    return TodayTodoList(
        entity_id=entity_id,
        label=label,
        items=[
            _todo_item(item)
            for item in raw_items
            if str(item.get("summary") or "").strip()
            and str(item.get("status") or "needs_action") == "needs_action"
        ],
    )


async def _weather_forecasts(
    ha: HomeAssistantService, entity_id: str, forecast_type: str
) -> list[TodayWeatherForecast]:
    if not entity_id:
        return []
    try:
        raw_forecasts = await ha.weather_forecasts(
            entity_id, forecast_type=forecast_type, timeout=_SOURCE_TIMEOUT
        )
    except (HomeAssistantError, httpx.HTTPError):
        return []
    return [forecast for raw in raw_forecasts if (forecast := _weather_forecast(raw)) is not None]


async def _weather(ha: HomeAssistantService, entity_id: str, state: HAState | None) -> TodayWeather:
    hourly, daily = await asyncio.gather(
        _weather_forecasts(ha, entity_id, "hourly"),
        _weather_forecasts(ha, entity_id, "daily"),
    )
    return TodayWeather(
        entity_id=entity_id,
        condition=state.state if state else "unknown",
        temperature=_float_value(state.attributes, "temperature") if state else None,
        precipitation_probability=hourly[0].precipitation_probability if hourly else None,
        humidity=_float_value(state.attributes, "humidity") if state else None,
        wind_speed=_float_value(state.attributes, "wind_speed") if state else None,
        hourly=hourly[:_HOURLY_FORECAST_LIMIT],
        daily=daily[:_DAILY_FORECAST_LIMIT],
    )


async def _overview(config: VaultConfig, ha: HomeAssistantService) -> TodayOverview:
    today_config = config.kiosk_today
    weather_entity_id = config.kiosk_home.weather.entity_id
    tz = ZoneInfo("Europe/Berlin")
    start_dt = datetime.now(tz)
    end_dt = start_dt + timedelta(days=_CALENDAR_LOOKAHEAD_DAYS)

    # Labels + news are cheap state reads; tolerate a hiccup rather than 502.
    try:
        states = await ha.states(
            today_config.calendar_entities
            + today_config.todo_entities
            + [weather_entity_id, today_config.news_headline_entity, today_config.news_summary_entity]
        )
    except HomeAssistantError:
        states = {}

    start_iso, end_iso = start_dt.isoformat(), end_dt.isoformat()
    calendar_results, todos, weather = await asyncio.gather(
        asyncio.gather(
            *(
                _calendar_events(ha, eid, _friendly_name(states.get(eid), eid), start_iso, end_iso)
                for eid in today_config.calendar_entities
            )
        ),
        asyncio.gather(
            *(_todo_list(ha, eid, _friendly_name(states.get(eid), eid)) for eid in today_config.todo_entities)
        ),
        _weather(ha, weather_entity_id, states.get(weather_entity_id)),
    )
    events = [event for sub in calendar_results for event in sub]
    events.sort(key=lambda event: event.start)

    headline_state = states.get(today_config.news_headline_entity)
    summary_state = states.get(today_config.news_summary_entity)
    return TodayOverview(
        events=events[:4],
        todos=list(todos),
        weather=weather,
        news=TodayNews(
            headline=headline_state.state if headline_state else None,
            summary=summary_state.state if summary_state else None,
        ),
    )


@router.get("/overview", response_model=TodayOverview)
async def overview(
    config: VaultConfig = Depends(get_config),
    ha: HomeAssistantService = Depends(get_homeassistant),
) -> TodayOverview:
    try:
        return await _overview(config, ha)
    except HomeAssistantError as exc:
        raise _ha_error(exc) from exc


@router.post("/todo/{entity_id}/item", response_model=TodayOverview)
async def update_todo_item(
    entity_id: str,
    body: TodayTodoUpdate,
    config: VaultConfig = Depends(get_config),
    ha: HomeAssistantService = Depends(get_homeassistant),
) -> TodayOverview:
    entity_id = entity_id.replace("__", ".")
    if entity_id not in config.kiosk_today.todo_entities:
        raise HTTPException(status_code=404, detail="Todo-Liste nicht für den Kiosk freigegeben")
    if body.status not in {"needs_action", "completed"}:
        raise HTTPException(status_code=422, detail="Ungültiger Todo-Status")
    try:
        await ha.update_todo_item(entity_id, item=body.item, status=body.status)
        return await _overview(config, ha)
    except HomeAssistantError as exc:
        raise _ha_error(exc) from exc
