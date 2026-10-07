"""In-memory Home Assistant used only by explicit simulation/test fixtures."""

from copy import deepcopy

from home_assistant import HomeAssistant
from home_assistant_api import HAError, HomeAssistantAPI


class InMemoryAliases:
    def __init__(self):
        self.rows = {}

    def run(self, action, alias="", target=None):
        if action == "remember":
            self.rows[alias] = target
        elif action == "forget":
            self.rows.pop(alias, None)
        return deepcopy(self.rows)


class FixtureAPI(HomeAssistantAPI):
    def __init__(self, fixture="ha_environment"):
        super().__init__("http://simulation.invalid", "fixture-only-token")
        self.fixture = fixture
        self.events = []
        self.rows = {
            "sensor.desk_temperature": {
                "entity_id": "sensor.desk_temperature",
                "state": "22.4",
                "attributes": {
                    "friendly_name": "Desk temperature",
                    "device_class": "temperature",
                    "unit_of_measurement": "°C",
                },
            },
            "sensor.desk_humidity": {
                "entity_id": "sensor.desk_humidity",
                "state": "46",
                "attributes": {
                    "friendly_name": "Desk humidity",
                    "device_class": "humidity",
                    "unit_of_measurement": "%",
                },
            },
            "sensor.lounge_temperature": {
                "entity_id": "sensor.lounge_temperature",
                "state": "20.1",
                "attributes": {
                    "friendly_name": "Lounge temperature",
                    "device_class": "temperature",
                    "unit_of_measurement": "°C",
                },
            },
            "light.desk_led": {
                "entity_id": "light.desk_led",
                "state": "off",
                "attributes": {
                    "friendly_name": "Desk lights",
                    "brightness": 0,
                    "supported_features": 40,
                },
            },
            "switch.desk_socket": {
                "entity_id": "switch.desk_socket",
                "state": "off",
                "attributes": {"friendly_name": "Desk socket"},
            },
        }
        self.registry = {
            "area": [
                {"area_id": "bedroom", "name": "Bedroom", "aliases": ["my room"]},
                {"area_id": "lounge", "name": "Living room"},
            ],
            "device": [
                {"id": "desk", "name_by_user": "Desk sensor", "area_id": "bedroom"},
                {"id": "lounge_sensor", "name": "Lounge sensor", "area_id": "lounge"},
            ],
            "entity": [
                {
                    "id": "stable-" + eid,
                    "entity_id": eid,
                    "device_id": "lounge_sensor" if "lounge" in eid else "desk",
                    "original_name": row["attributes"]["friendly_name"],
                    "aliases": ["LEDs"] if eid == "light.desk_led" else [],
                }
                for eid, row in self.rows.items()
            ],
        }
        if fixture == "ha_ambiguous":
            self.rows["sensor.window_temperature"] = {
                "entity_id": "sensor.window_temperature",
                "state": "21.1",
                "attributes": {
                    "friendly_name": "Window temperature",
                    "device_class": "temperature",
                    "unit_of_measurement": "°C",
                },
            }
            self.registry["entity"].append(
                {
                    "id": "window",
                    "entity_id": "sensor.window_temperature",
                    "area_id": "bedroom",
                }
            )

    async def registries(self):
        self.events.append(("registry", "read"))
        return deepcopy(self.registry)

    async def registry_entity(self, entity_id):
        return deepcopy(
            next(
                (r for r in self.registry["entity"] if r["entity_id"] == entity_id), {}
            )
        )

    async def request(self, method, path, data=None):
        self.events.append((method, path, deepcopy(data)))
        if path == "/api/states":
            return deepcopy(list(self.rows.values()))
        if path.startswith("/api/states/"):
            if self.fixture == "ha_timeout" and any(
                e[0] == "POST" for e in self.events
            ):
                raise HAError("offline")
            eid = path.removeprefix("/api/states/")
            if eid not in self.rows:
                raise HAError("missing")
            return deepcopy(self.rows[eid])
        if method == "POST" and path.startswith("/api/services/"):
            if self.fixture == "ha_timeout":
                raise HAError("timeout", True)
            eid = data["entity_id"]
            self.rows[eid]["state"] = "on" if path.endswith("turn_on") else "off"
            return []
        raise AssertionError("Unexpected simulated HA request")


def fixture_client(fixture="ha_environment"):
    api = FixtureAPI(fixture)
    return HomeAssistant(api, InMemoryAliases()), api
