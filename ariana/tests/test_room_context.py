import time
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from home_assistant_simulation import fixture_client


def configured():
    client, api = fixture_client()
    now = time.time()
    for row in api.rows.values():
        row["last_reported"] = datetime.fromtimestamp(now, timezone.utc).isoformat()
    for eid, state, attributes in [
        ("binary_sensor.desk_motion", "off", {"device_class": "motion"}),
        ("binary_sensor.desk_presence", "on", {"device_class": "occupancy"}),
        (
            "sensor.desk_lux",
            "24",
            {"device_class": "illuminance", "unit_of_measurement": "lx"},
        ),
        (
            "automation.desk_lighting",
            "on",
            {
                "last_triggered": datetime.fromtimestamp(
                    now - 120, timezone.utc
                ).isoformat(),
                "action": "private content",
            },
        ),
    ]:
        api.rows[eid] = {
            "entity_id": eid,
            "state": state,
            "attributes": attributes,
            "last_reported": datetime.fromtimestamp(now, timezone.utc).isoformat(),
        }
        api.registry["entity"].append(
            {
                "id": "stable-" + eid,
                "entity_id": eid,
                "area_id": "bedroom",
                "platform": "test",
            }
        )
    return client, api


@pytest.mark.asyncio
async def test_combines_only_selected_area_with_freshness_and_no_writes():
    client, api = configured()
    result = await client.room_context("my room")
    assert result["area"]["id"] == "bedroom"
    observations = {row["entity_id"]: row for row in result["observations"]}
    assert observations["sensor.desk_temperature"]["state"] == "22.4"
    assert observations["sensor.desk_lux"]["unit"] == "lx"
    assert observations["binary_sensor.desk_presence"]["category"] == "occupancy"
    assert observations["binary_sensor.desk_motion"]["category"] == "motion"
    assert observations["automation.desk_lighting"]["last_triggered_at"]
    assert "private content" not in str(result)
    assert "sensor.lounge_temperature" not in observations
    assert not any(event[0] == "POST" for event in api.events)
    assert result["identity"] == "unknown"


@pytest.mark.asyncio
async def test_stale_future_unknown_and_assumed_readings_are_not_current_facts():
    client, api = configured()
    api.rows["sensor.desk_temperature"]["last_reported"] = "2000-01-01T00:00:00+00:00"
    api.rows["sensor.desk_humidity"]["last_reported"] = "2999-01-01T00:00:00+00:00"
    api.rows["binary_sensor.desk_presence"]["state"] = "unavailable"
    api.rows["light.desk_led"]["attributes"]["assumed_state"] = True
    result = await client.room_context("Bedroom")
    readings = {row["entity_id"]: row for row in result["observations"]}
    for entity in [
        "sensor.desk_temperature",
        "sensor.desk_humidity",
        "binary_sensor.desk_presence",
        "light.desk_led",
    ]:
        assert readings[entity]["verified"] is False
        assert readings[entity]["state"] is None
    assert result["partial"]


@pytest.mark.asyncio
async def test_ambiguous_area_and_missing_registry_never_expand_to_whole_home():
    client, api = configured()
    api.registry["area"].append({"area_id": "spare", "name": "Bedroom"})
    result = await client.room_context("Bedroom")
    assert result["status"] == "ambiguous"
    assert "observations" not in result
    api.registry.clear()
    result = await client.room_context("Bedroom")
    assert result["status"] == "not_found"
    assert "observations" not in result


@pytest.mark.asyncio
async def test_room_overview_is_bounded_and_does_not_starve_sensor_categories():
    client, api = configured()
    for i in range(30):
        eid = f"sensor.extra_temperature_{i}"
        api.rows[eid] = {**api.rows["sensor.desk_temperature"], "entity_id": eid}
        api.registry["entity"].append(
            {"id": eid, "entity_id": eid, "area_id": "bedroom"}
        )
    result = await client.room_context("Bedroom")
    assert result["omitted_count"] > 0
    assert len(result["observations"]) <= 18
    assert any(row["category"] == "light" for row in result["observations"])
    assert any(row["category"] == "occupancy" for row in result["observations"])


@pytest.mark.asyncio
async def test_camera_fusion_requires_opt_in_and_uses_existing_privacy_gate(
    monkeypatch,
):
    import camera_awareness
    from home_assistant_tools import home_assistant_room_context

    client, api = configured()
    eid = "sensor.bedroom_person_count"
    api.rows[eid] = {
        "entity_id": eid,
        "state": "1",
        "attributes": {
            "friendly_name": "Bedroom person count",
            "unit_of_measurement": "objects",
        },
    }
    api.registry["entity"].append(
        {"id": "count", "entity_id": eid, "area_id": "bedroom", "platform": "frigate"}
    )
    read = AsyncMock(
        return_value={"error": "Camera access is disabled.", "verified": False}
    )
    monkeypatch.setattr(camera_awareness, "read_camera", read)
    ctx = SimpleNamespace(session=SimpleNamespace(userdata={"_ha_client": client}))
    result = await home_assistant_room_context._func(ctx, "Bedroom")
    assert result["camera"]["status"] == "not_requested"
    read.assert_not_awaited()
    result = await home_assistant_room_context._func(
        ctx, "Bedroom", include_camera=True
    )
    read.assert_awaited_once_with(ctx, "current", "", eid)
    assert "disabled" in result["camera"]["error"]
    assert result["identity"] == "unknown"
    assert "_camera_sources" not in result


@pytest.mark.asyncio
async def test_real_camera_disable_gate_prevents_frigate_access(monkeypatch):
    from home_assistant_tools import home_assistant_room_context

    monkeypatch.delenv("ARIANA_CAMERA_ENABLED", raising=False)
    client, api = configured()
    eid = "sensor.bedroom_person_count"
    api.rows[eid] = {
        "entity_id": eid,
        "state": "1",
        "attributes": {
            "friendly_name": "Bedroom person count",
            "unit_of_measurement": "objects",
        },
    }
    api.registry["entity"].append(
        {"id": "count", "entity_id": eid, "area_id": "bedroom", "platform": "frigate"}
    )
    ctx = SimpleNamespace(session=SimpleNamespace(userdata={"_ha_client": client}))
    result = await home_assistant_room_context._func(
        ctx, "Bedroom", include_camera=True
    )
    assert "disabled" in result["camera"]["error"]
    assert "_camera_client" not in ctx.session.userdata
    assert result["partial"]


@pytest.mark.asyncio
async def test_fresh_registry_scope_drops_entities_moved_since_last_query():
    client, api = configured()
    await client.room_context("Bedroom")
    for row in api.registry["entity"]:
        if row["entity_id"] == "sensor.desk_temperature":
            row["area_id"] = "lounge"
    result = await client.room_context("Bedroom")
    assert "sensor.desk_temperature" not in {
        row["entity_id"] for row in result["observations"]
    }


@pytest.mark.asyncio
async def test_room_simulation_requires_real_snapshot_and_rejects_device_effects():
    from unittest.mock import Mock

    from simulation_tools import check_simulation_state

    client, api = fixture_client("ha_room_context")
    ctx = SimpleNamespace(
        userdata=lambda: {"fixture": "ha_room_context"},
        job_context=SimpleNamespace(
            primary_session=SimpleNamespace(userdata={"ha_api": api})
        ),
        fail=Mock(),
    )
    await check_simulation_state(ctx)
    assert ctx.fail.called
    ctx.fail.reset_mock()
    await client.room_context("Bedroom")
    await check_simulation_state(ctx)
    ctx.fail.assert_not_called()
    api.events.append(
        ("POST", "/api/services/light/turn_on", {"entity_id": "light.desk_led"})
    )
    await check_simulation_state(ctx)
    assert ctx.fail.called
