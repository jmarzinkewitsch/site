import json

import httpx

import deps
from config import ServiceConfig
from services.homeassistant import HAState
from services.homeassistant import HomeAssistantService


class FakeTodayHomeAssistant:
    def __init__(self):
        self.state_map = {
            "calendar.privat": HAState("calendar.privat", "off", {"friendly_name": "Privat"}),
            "todo.einkaufsliste": HAState("todo.einkaufsliste", "1", {"friendly_name": "Einkaufsliste"}),
            "weather.wetter_in_hamburg": HAState(
                "weather.wetter_in_hamburg",
                "partlycloudy",
                {"temperature": "18.5", "humidity": 64, "wind_speed": "14"},
            ),
            "input_text.hamburg_news_headline": HAState("input_text.hamburg_news_headline", "Headline", {}),
            "input_text.hamburg_news_summary": HAState("input_text.hamburg_news_summary", "Zusammenfassung", {}),
        }
        self.calls = []

    async def states(self, entity_ids):
        return {entity_id: self.state_map[entity_id] for entity_id in entity_ids if entity_id in self.state_map}

    async def calendar_events(self, entity_id, *, start, end, timeout=None):
        assert entity_id == "calendar.privat"
        return [
            {
                "summary": "Zahnarzt",
                "start": {"dateTime": "2026-06-23T14:30:00+02:00"},
                "end": {"dateTime": "2026-06-23T15:00:00+02:00"},
                "location": "Hamburg",
            }
        ]

    async def todo_items(self, entity_id, *, status="needs_action", timeout=None):
        assert entity_id == "todo.einkaufsliste"
        return [{"uid": "todo-1", "summary": "Milch", "status": "needs_action"}]

    async def weather_forecasts(self, entity_id, *, forecast_type, timeout=None):
        assert entity_id == "weather.wetter_in_hamburg"
        if forecast_type == "hourly":
            return [
                {
                    "datetime": "2026-06-23T15:00:00+02:00",
                    "condition": "rainy",
                    "temperature": 17,
                    "precipitation_probability": 60,
                },
                {
                    "datetime": "2026-06-23T18:00:00+02:00",
                    "condition": "cloudy",
                    "temperature": 16,
                    "precipitation_probability": 30,
                },
            ]
        assert forecast_type == "daily"
        return [
            {
                "datetime": "2026-06-24T00:00:00+02:00",
                "condition": "sunny",
                "temperature": 21,
                "templow": 12,
                "precipitation_probability": 10,
            },
            {
                "datetime": "2026-06-25T00:00:00+02:00",
                "condition": "partlycloudy",
                "temperature": 20,
                "templow": 11,
                "precipitation_probability": 20,
            },
        ]

    async def update_todo_item(self, entity_id, *, item, status):
        self.calls.append((entity_id, item, status))


def _configure_today(store):
    store.update(
        kiosk_today={
            "calendar_entities": ["calendar.privat"],
            "todo_entities": ["todo.einkaufsliste"],
            "news_headline_entity": "input_text.hamburg_news_headline",
            "news_summary_entity": "input_text.hamburg_news_summary",
        }
    )


def test_today_requires_bearer(client):
    assert client.get("/today/overview").status_code == 401


def test_today_overview_accepts_kiosk_token_and_maps_curated_data(client, store):
    _configure_today(store)
    store.update(kiosk_token="kiosk-today-token")
    fake = FakeTodayHomeAssistant()
    client.app.dependency_overrides[deps.get_homeassistant] = lambda: fake
    try:
        r = client.get("/today/overview", headers={"Authorization": "Bearer kiosk-today-token"})
    finally:
        client.app.dependency_overrides.pop(deps.get_homeassistant, None)

    assert r.status_code == 200
    body = r.json()
    assert body["events"][0]["summary"] == "Zahnarzt"
    assert body["events"][0]["calendar_label"] == "Privat"
    assert body["todos"][0]["items"][0]["summary"] == "Milch"
    weather = body["weather"]
    assert weather["entity_id"] == "weather.wetter_in_hamburg"
    assert weather["condition"] == "partlycloudy"
    assert weather["temperature"] == 18.5
    assert weather["precipitation_probability"] == 60.0
    assert weather["humidity"] == 64.0
    assert weather["wind_speed"] == 14.0
    assert [(forecast["datetime"], forecast["condition"]) for forecast in weather["hourly"]] == [
        ("2026-06-23T15:00:00+02:00", "rainy"),
        ("2026-06-23T18:00:00+02:00", "cloudy"),
    ]
    assert [(forecast["datetime"], forecast["templow"]) for forecast in weather["daily"]] == [
        ("2026-06-24T00:00:00+02:00", 12.0),
        ("2026-06-25T00:00:00+02:00", 11.0),
    ]
    assert body["news"] == {"headline": "Headline", "summary": "Zusammenfassung"}


def test_today_todo_update_calls_configured_list_and_returns_overview(client, auth, store):
    _configure_today(store)
    fake = FakeTodayHomeAssistant()
    client.app.dependency_overrides[deps.get_homeassistant] = lambda: fake
    try:
        r = client.post(
            "/today/todo/todo__einkaufsliste/item",
            headers=auth,
            json={"item": "todo-1", "status": "completed"},
        )
    finally:
        client.app.dependency_overrides.pop(deps.get_homeassistant, None)

    assert r.status_code == 200
    assert fake.calls == [("todo.einkaufsliste", "todo-1", "completed")]


class FlakyTodayHomeAssistant(FakeTodayHomeAssistant):
    def __init__(self):
        super().__init__()
        self.state_map["calendar.kaputt"] = HAState("calendar.kaputt", "off", {"friendly_name": "Kaputt"})

    async def calendar_events(self, entity_id, *, start, end, timeout=None):
        from services.homeassistant import HomeAssistantError

        if entity_id == "calendar.kaputt":
            raise HomeAssistantError("Timeout", status_code=502)
        return await super().calendar_events(entity_id, start=start, end=end, timeout=timeout)


def test_today_tolerates_a_single_broken_calendar(client, store):
    store.update(
        kiosk_today={
            "calendar_entities": ["calendar.kaputt", "calendar.privat"],
            "todo_entities": ["todo.einkaufsliste"],
            "news_headline_entity": "input_text.hamburg_news_headline",
            "news_summary_entity": "input_text.hamburg_news_summary",
        },
        kiosk_token="kiosk-today-token",
    )
    fake = FlakyTodayHomeAssistant()
    client.app.dependency_overrides[deps.get_homeassistant] = lambda: fake
    try:
        r = client.get("/today/overview", headers={"Authorization": "Bearer kiosk-today-token"})
    finally:
        client.app.dependency_overrides.pop(deps.get_homeassistant, None)

    # The broken calendar drops out; the working one and the rest still render.
    assert r.status_code == 200
    body = r.json()
    assert [event["summary"] for event in body["events"]] == ["Zahnarzt"]
    assert body["todos"][0]["items"][0]["summary"] == "Milch"


class UpcomingEventsTodayHomeAssistant(FakeTodayHomeAssistant):
    def __init__(self):
        super().__init__()
        self.state_map["calendar.arbeit"] = HAState("calendar.arbeit", "off", {"friendly_name": "Arbeit"})

    async def calendar_events(self, entity_id, *, start, end, timeout=None):
        events = {
            "calendar.privat": [
                {"summary": "Abendessen", "start": {"dateTime": "2026-06-27T19:00:00+02:00"}},
                {"summary": "Arzt", "start": {"dateTime": "2026-06-25T09:00:00+02:00"}},
                {"summary": "Kino", "start": {"dateTime": "2026-06-29T20:00:00+02:00"}},
            ],
            "calendar.arbeit": [
                {"summary": "Stand-up", "start": {"dateTime": "2026-06-24T09:30:00+02:00"}},
                {"summary": "Planung", "start": {"dateTime": "2026-06-26T10:00:00+02:00"}},
            ],
        }
        return events[entity_id]


def test_today_overview_returns_the_next_four_events_across_calendars(client, auth, store):
    store.update(
        kiosk_today={
            "calendar_entities": ["calendar.privat", "calendar.arbeit"],
            "todo_entities": ["todo.einkaufsliste"],
        }
    )
    fake = UpcomingEventsTodayHomeAssistant()
    client.app.dependency_overrides[deps.get_homeassistant] = lambda: fake
    try:
        r = client.get("/today/overview", headers=auth)
    finally:
        client.app.dependency_overrides.pop(deps.get_homeassistant, None)

    assert r.status_code == 200
    body = r.json()
    assert [event["summary"] for event in body["events"]] == ["Stand-up", "Arzt", "Planung", "Abendessen"]


async def test_homeassistant_todo_items_accepts_service_response_and_direct_entity_response():
    entity_id = "todo.einkaufsliste"
    responses = [
        {"service_response": {entity_id: {"items": [{"summary": "Milch"}]}}},
        {entity_id: {"items": [{"summary": "Brot"}]}},
    ]
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=responses.pop(0))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        ha = HomeAssistantService(ServiceConfig(base_url="http://ha.local", api_key="token"), http)
        assert await ha.todo_items(entity_id) == [{"summary": "Milch"}]
        assert await ha.todo_items(entity_id) == [{"summary": "Brot"}]

    assert requests[0].url.path == "/api/services/todo/get_items"
    assert requests[0].url.params["return_response"] == ""
    assert json.loads(requests[0].content) == {"entity_id": entity_id, "status": "needs_action"}


async def test_homeassistant_weather_forecasts_calls_the_weather_service_and_maps_the_entity_response():
    entity_id = "weather.wetter_in_hamburg"
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "service_response": {
                    entity_id: {"forecast": [{"datetime": "2026-06-24T12:00:00+02:00", "temperature": 20}]}
                }
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        ha = HomeAssistantService(ServiceConfig(base_url="http://ha.local", api_key="token"), http)
        forecast = await ha.weather_forecasts(entity_id, forecast_type="hourly", timeout=4)

    assert forecast == [{"datetime": "2026-06-24T12:00:00+02:00", "temperature": 20}]
    assert requests[0].url.path == "/api/services/weather/get_forecasts"
    assert requests[0].url.params["return_response"] == ""
    assert json.loads(requests[0].content) == {"entity_id": entity_id, "type": "hourly"}
