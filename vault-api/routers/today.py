from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, Depends, HTTPException

from auth import require_bearer_or_kiosk
from config import KioskTodayConfig, VaultConfig
from deps import get_config, get_homeassistant
from models import TodayEvent, TodayNews, TodayOverview, TodayTodoItem, TodayTodoList, TodayTodoUpdate
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


# Per-source timeout so one slow HA calendar/todo backend can't stall — or 502 —
# the whole Heute page. Each source is fetched concurrently and failures are
# tolerated: a broken calendar just drops out instead of killing the overview.
_SOURCE_TIMEOUT = 8.0


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
        items=[_todo_item(item) for item in raw_items],
    )


async def _overview(config: KioskTodayConfig, ha: HomeAssistantService) -> TodayOverview:
    tz = ZoneInfo("Europe/Berlin")
    start_dt = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
    end_dt = start_dt + timedelta(days=1)

    # Labels + news are cheap state reads; tolerate a hiccup rather than 502.
    try:
        states = await ha.states(
            config.calendar_entities
            + config.todo_entities
            + [config.news_headline_entity, config.news_summary_entity]
        )
    except HomeAssistantError:
        states = {}

    start_iso, end_iso = start_dt.isoformat(), end_dt.isoformat()
    calendar_results, todos = await asyncio.gather(
        asyncio.gather(
            *(
                _calendar_events(ha, eid, _friendly_name(states.get(eid), eid), start_iso, end_iso)
                for eid in config.calendar_entities
            )
        ),
        asyncio.gather(
            *(_todo_list(ha, eid, _friendly_name(states.get(eid), eid)) for eid in config.todo_entities)
        ),
    )
    events = [event for sub in calendar_results for event in sub]
    events.sort(key=lambda event: event.start)

    headline_state = states.get(config.news_headline_entity)
    summary_state = states.get(config.news_summary_entity)
    return TodayOverview(
        events=events[:12],
        todos=list(todos),
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
        return await _overview(config.kiosk_today, ha)
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
        return await _overview(config.kiosk_today, ha)
    except HomeAssistantError as exc:
        raise _ha_error(exc) from exc
