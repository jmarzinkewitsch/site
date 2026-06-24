import deps
from services.homeassistant import HAState


class FakeHomeAssistant:
    def __init__(self):
        self.state_map = {
            "scene.wohnzimmer_couch": HAState("scene.wohnzimmer_couch", "on", {"friendly_name": "Wohnzimmer Couch"}),
            "scene.wohnzimmer_aus": HAState("scene.wohnzimmer_aus", "off", {"friendly_name": "Wohnzimmer Aus"}),
            "scene.kueche_an": HAState("scene.kueche_an", "on", {"friendly_name": "Küche An"}),
            "light.wohnzimmer_decke": HAState("light.wohnzimmer_decke", "on", {"friendly_name": "Wohnzimmer Decke"}),
            "light.wohnzimmer_stehlampe": HAState("light.wohnzimmer_stehlampe", "off", {"friendly_name": "Wohnzimmer Stehlampe"}),
            "light.kueche_decke": HAState("light.kueche_decke", "on", {"friendly_name": "Küche Decke"}),
            "light.kueche_arbeitsplatte": HAState("light.kueche_arbeitsplatte", "on", {"friendly_name": "Küche Arbeitsplatte"}),
            "climate.wohnzimmer": HAState(
                "climate.wohnzimmer",
                "heat",
                {"friendly_name": "Wohnzimmer", "current_temperature": 20.8, "temperature": 21.5, "preset_mode": "comfort"},
            ),
            "switch.kaffeemaschine": HAState("switch.kaffeemaschine", "off", {"friendly_name": "Kaffeemaschine"}),
            "weather.wetter_in_hamburg": HAState("weather.wetter_in_hamburg", "cloudy", {"temperature": 18}),
            "binary_sensor.fenster_bad": HAState("binary_sensor.fenster_bad", "on", {"friendly_name": "Bad-Fenster"}),
        }
        self.calls = []

    async def states(self, entity_ids):
        return {entity_id: self.state_map[entity_id] for entity_id in entity_ids if entity_id in self.state_map}

    async def call_service(self, service, *, entity_id, data=None):
        self.calls.append((service, entity_id, data))
        if entity_id == "switch.kaffeemaschine":
            self.state_map[entity_id] = HAState(entity_id, "on", {"friendly_name": "Kaffeemaschine"})
        if entity_id == "climate.wohnzimmer" and data and "temperature" in data:
            current = self.state_map[entity_id]
            attrs = dict(current.attributes)
            attrs["temperature"] = data["temperature"]
            self.state_map[entity_id] = HAState(entity_id, current.state, attrs)


def _configure_kiosk_home(store):
    store.update(
        kiosk_home={
            "lights": [
                {
                    "id": "wohnzimmer",
                    "label": "Wohnzimmer",
                    "status_entity_ids": ["light.wohnzimmer_decke", "light.wohnzimmer_stehlampe"],
                    "scenes": [
                        {
                            "id": "couch",
                            "label": "Couch",
                            "entity_id": "scene.wohnzimmer_couch",
                            "active_state": "on",
                        },
                        {
                            "id": "aus",
                            "label": "Aus",
                            "entity_id": "scene.wohnzimmer_aus",
                            "active_state": "on",
                        },
                    ],
                },
                {
                    "id": "kueche",
                    "label": "Küche",
                    "status_entity_ids": ["light.kueche_decke", "light.kueche_arbeitsplatte"],
                    "scenes": [
                        {
                            "id": "an",
                            "label": "An",
                            "entity_id": "scene.kueche_an",
                            "active_state": "on",
                        }
                    ],
                },
            ],
            "climates": [{"id": "wohnzimmer", "label": "Wohnzimmer", "entity_id": "climate.wohnzimmer"}],
            "coffee": {"label": "Kaffeemaschine", "entity_id": "switch.kaffeemaschine"},
            "weather": {"entity_id": "weather.wetter_in_hamburg"},
            "window_entities": ["binary_sensor.fenster_bad"],
        }
    )


def test_home_requires_bearer(client):
    assert client.get("/home/overview").status_code == 401


def test_home_accepts_scoped_kiosk_token(client, store):
    _configure_kiosk_home(store)
    store.update(kiosk_token="kiosk-token")
    fake = FakeHomeAssistant()
    client.app.dependency_overrides[deps.get_homeassistant] = lambda: fake
    try:
        r = client.get("/home/overview", headers={"Authorization": "Bearer kiosk-token"})
    finally:
        client.app.dependency_overrides.pop(deps.get_homeassistant, None)

    assert r.status_code == 200
    assert r.json()["coffee"]["entity_id"] == "switch.kaffeemaschine"


def test_home_overview_is_curated(client, auth, store):
    _configure_kiosk_home(store)
    fake = FakeHomeAssistant()
    client.app.dependency_overrides[deps.get_homeassistant] = lambda: fake
    try:
        r = client.get("/home/overview", headers=auth)
    finally:
        client.app.dependency_overrides.pop(deps.get_homeassistant, None)

    assert r.status_code == 200
    body = r.json()
    assert body["lights_on"] == 3
    assert body["windows_open"] == 1
    assert body["weather"] == {"entity_id": "weather.wetter_in_hamburg", "state": "cloudy", "temperature": 18.0}
    assert body["lights"][0]["state"] == "an"
    assert body["lights"][0]["scenes"][0]["active"] is True
    assert body["climates"][0]["target_temperature"] == 21.5
    assert body["coffee"]["on"] is False


def test_activate_light_scene_calls_configured_service(client, auth, store):
    _configure_kiosk_home(store)
    fake = FakeHomeAssistant()
    client.app.dependency_overrides[deps.get_homeassistant] = lambda: fake
    try:
        r = client.post("/home/lights/wohnzimmer/scenes/couch", headers=auth)
    finally:
        client.app.dependency_overrides.pop(deps.get_homeassistant, None)

    assert r.status_code == 204
    assert fake.calls == [("scene.turn_on", "scene.wohnzimmer_couch", None)]


def test_set_climate_uses_ha_climate_service_and_returns_overview(client, auth, store):
    _configure_kiosk_home(store)
    fake = FakeHomeAssistant()
    client.app.dependency_overrides[deps.get_homeassistant] = lambda: fake
    try:
        r = client.post("/home/climate/wohnzimmer", headers=auth, json={"target_temperature": 22.0})
    finally:
        client.app.dependency_overrides.pop(deps.get_homeassistant, None)

    assert r.status_code == 200
    assert fake.calls == [("climate.set_temperature", "climate.wohnzimmer", {"temperature": 22.0})]
    assert r.json()["climates"][0]["target_temperature"] == 22.0


def test_set_coffee_toggles_switch_and_returns_overview(client, auth, store):
    _configure_kiosk_home(store)
    fake = FakeHomeAssistant()
    client.app.dependency_overrides[deps.get_homeassistant] = lambda: fake
    try:
        r = client.post("/home/coffee", headers=auth, json={"on": True})
    finally:
        client.app.dependency_overrides.pop(deps.get_homeassistant, None)

    assert r.status_code == 200
    assert fake.calls == [("switch.turn_on", "switch.kaffeemaschine", None)]
    assert r.json()["coffee"]["on"] is True
