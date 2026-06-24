import deps
from services.homeassistant import HAState


class FakeTodayHomeAssistant:
    def __init__(self):
        self.state_map = {
            "calendar.privat": HAState("calendar.privat", "off", {"friendly_name": "Privat"}),
            "todo.einkaufsliste": HAState("todo.einkaufsliste", "1", {"friendly_name": "Einkaufsliste"}),
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
