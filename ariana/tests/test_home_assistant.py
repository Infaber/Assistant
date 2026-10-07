from types import SimpleNamespace

import httpx
import pytest

from home_assistant import CACHE_SECONDS, matches, service_plan
from home_assistant_aliases import AliasStore
from home_assistant_api import HAError, HomeAssistantAPI, configuration
from home_assistant_simulation import fixture_client
from home_assistant_tools import home_assistant_control, home_assistant_request
from task_ledger import ledger_for


def context(client):
    return SimpleNamespace(
        session=SimpleNamespace(
            userdata={"_ha_client": client},
            history=SimpleNamespace(items=[SimpleNamespace(role="user", id="u1")]),
        )
    )


@pytest.mark.asyncio
async def test_room_temperature_and_humidity():
    client, _ = fixture_client()
    temp = await client.get_state("room temperature")
    humid = await client.get_state("my room", device_class="humidity")
    assert temp["state"] == "22.4" and temp["unit"] == "°C"
    assert humid["state"] == "46" and humid["unit"] == "%"
    assert temp["verified"] and humid["verified"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query, expected",
    [
        ("Bedroom temperature", "sensor.desk_temperature"),
        ("Living room temperature", "sensor.lounge_temperature"),
        ("Desk lights", "light.desk_led"),
        ("LEDs", "light.desk_led"),
        ("Desk socket", "switch.desk_socket"),
        ("Desk ligths", "light.desk_led"),
    ],
)
async def test_area_friendly_ha_alias_fuzzy(query, expected):
    client, _ = fixture_client()
    result = await client.find(query)
    assert result["status"] == "resolved", result
    assert result["entity"]["entity_id"] == expected


@pytest.mark.asyncio
async def test_multiple_temperature_sensors_require_disambiguation():
    client, api = fixture_client("ha_ambiguous")
    result = await client.get_state("bedroom temperature")
    assert result["status"] == "ambiguous" and result["candidate_count"] == 2
    assert not any(
        e[0] == "GET" and e[1].startswith("/api/states/sensor.") for e in api.events
    )


@pytest.mark.asyncio
async def test_private_aliases_entity_area_device_and_forget(tmp_path):
    client, api = fixture_client()
    client.aliases = AliasStore(api.url, tmp_path / "aliases.sqlite3")
    for alias, target, kind in [
        ("my room", "Bedroom", "area"),
        ("desk glow", "Desk lights", "entity"),
        ("environment", "Desk sensor", "device"),
    ]:
        result = await client.alias("remember", alias, target, kind)
        assert result["saved"]
    assert (await client.get_state("my room", device_class="humidity"))["state"] == "46"
    assert (await client.find("desk glow"))["entity"]["entity_id"] == "light.desk_led"
    assert (await client.get_state("environment", device_class="temperature"))[
        "state"
    ] == "22.4"
    assert (client.aliases.path.stat().st_mode & 0o777) == 0o600
    other = AliasStore("http://different.invalid", client.aliases.path)
    assert other.run("recall") == {}
    await client.alias("forget", "desk glow")
    assert "desk glow" not in await client.mappings()


@pytest.mark.asyncio
async def test_saved_alias_survives_entity_rename_and_never_uses_removed_id():
    client, api = fixture_client()
    await client.alias("remember", "desk glow", "Desk lights")
    row = api.rows.pop("light.desk_led")
    row["entity_id"] = "light.renamed"
    api.rows["light.renamed"] = row
    reg = next(r for r in api.registry["entity"] if r["entity_id"] == "light.desk_led")
    reg["entity_id"] = "light.renamed"
    client.refreshed = -float("inf")
    assert (await client.find("desk glow"))["entity"]["entity_id"] == "light.renamed"
    api.rows.pop("light.renamed")
    client.refreshed = -float("inf")
    result = await client.control(context(client), "desk glow", "on")
    assert result["code"] == "stale_alias"
    assert not any(e[0] == "POST" for e in api.events)


@pytest.mark.asyncio
async def test_unavailable_entities_do_not_trigger_services():
    client, api = fixture_client()
    api.rows["light.desk_led"]["state"] = "unavailable"
    assert (await client.get_state("Desk lights"))["code"] == "unavailable"
    assert (await client.control(context(client), "Desk lights", "on"))[
        "code"
    ] == "unavailable"
    assert not any(e[0] == "POST" for e in api.events)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "target,domain", [("Desk lights", "light"), ("Desk socket", "switch")]
)
async def test_direct_control_and_fresh_state_verification(target, domain):
    client, api = fixture_client()
    ctx = context(client)
    result = await client.control(ctx, target, "on")
    assert result["verified"] and result["state"] == "on"
    posts = [e for e in api.events if e[0] == "POST"]
    assert len(posts) == 1 and posts[0][1] == f"/api/services/{domain}/turn_on"
    assert ledger_for(ctx).receipts[-1].write
    assert ledger_for(ctx).receipts[-1].status == "verified"
    # Synonyms don't dispatch a duplicate, and an already-on device is a read-only no-op.
    again = await client.control(ctx, target, "on")
    assert again["already_in_requested_state"]
    assert len([e for e in api.events if e[0] == "POST"]) == 1
    fallback = await home_assistant_request._func(ctx, "Turn it on")
    assert "direct" in fallback["error"]


@pytest.mark.asyncio
async def test_dispatched_timeout_uncertain_and_synonym_retries_blocked():
    client, api = fixture_client("ha_timeout")
    ctx = context(client)
    result = await client.control(ctx, "desk lights", "on")
    assert result["uncertain"] and "may have reached" in result["error"]
    again = await client.control(ctx, "LEDs", "on")
    assert again["uncertain"]
    fallback = await home_assistant_request._func(ctx, "Turn off the LEDs")
    assert fallback["uncertain"]
    assert len([e for e in api.events if e[0] == "POST"]) == 1
    assert ledger_for(ctx).receipts[0].status == "uncertain"


@pytest.mark.asyncio
async def test_uncertain_read_reconciliation_is_observation_not_replay():
    client, api = fixture_client("ha_timeout")
    ctx = context(client)
    await client.control(ctx, "desk lights", "on")
    api.fixture = "ha_environment"
    api.rows["light.desk_led"]["state"] = "on"
    result = await client.get_state("LEDs")
    assert result["verified_action_id"]
    assert ledger_for(ctx).receipts[-1].status == "verified"
    assert len([e for e in api.events if e[0] == "POST"]) == 1


@pytest.mark.asyncio
async def test_returned_service_is_not_success_until_expected_state_observed():
    client, api = fixture_client()
    original = api.request

    async def slow(method, path, data=None):
        if method == "POST":
            api.events.append((method, path, data))
            return []
        return await original(method, path, data)

    api.request = slow
    ctx = context(client)
    result = await client.control(ctx, "Desk lights", "on")
    assert not result["verified"]
    assert ledger_for(ctx).receipts[-1].status == "returned"
    assert (await client.control(ctx, "LEDs", "on"))["uncertain"]


@pytest.mark.asyncio
async def test_inventory_ttl_refresh_and_missing_state():
    client, api = fixture_client()
    clock = [0]
    client.clock = lambda: clock[0]
    await client.inventory()
    await client.find("desk")
    assert sum(e[1] == "/api/states" for e in api.events) == 1
    clock[0] = CACHE_SECONDS + 1
    await client.find("desk")
    assert sum(e[1] == "/api/states" for e in api.events) == 2
    clock[0] += 3
    await client.inventory(True)
    assert sum(e[1] == "/api/states" for e in api.events) == 3
    api.rows.pop("light.desk_led")
    clock[0] += 3
    with pytest.raises(HAError, match="missing"):
        await client.get_state("Desk lights")
    assert sum(e[1] == "/api/states" for e in api.events) == 4


@pytest.mark.asyncio
async def test_failed_lookup_refresh_is_bounded():
    client, api = fixture_client()
    await client.find("unknown target")
    for _ in range(5):
        await client.find("unknown target")
    assert sum(e[1] == "/api/states" for e in api.events) == 1


@pytest.mark.asyncio
async def test_registry_failure_degrades_to_names_without_inventing_area():
    client, api = fixture_client()

    async def denied():
        raise HAError("registry")

    api.registries = denied
    result = await client.find("Desk lights")
    assert result["status"] == "resolved" and result["warning"]
    assert result["entity"]["area"] == ""


@pytest.mark.asyncio
@pytest.mark.parametrize("code", ["offline", "auth", "timeout"])
async def test_tool_returns_safe_error_and_failure_backoff(code):
    client, api = fixture_client()

    async def fail(*args):
        api.events.append(("failed", code))
        raise HAError(code)

    api.request = fail
    ctx = context(client)
    result = await home_assistant_control._func(ctx, "Desk lights", "on")
    assert result["code"] == code and not result.get("uncertain")
    await home_assistant_control._func(ctx, "Desk lights", "on")
    assert len(api.events) == 1


def test_configuration_never_exports_url_or_token(monkeypatch):
    monkeypatch.setenv("HOME_ASSISTANT_URL", "https://user:credential@secret.invalid")
    monkeypatch.setenv("HOME_ASSISTANT_TOKEN", "credential")
    with pytest.raises(HAError) as exc:
        configuration()
    assert "credential" not in repr(exc.value.result())
    monkeypatch.delenv("HOME_ASSISTANT_TOKEN")
    with pytest.raises(HAError, match="configuration"):
        configuration()


@pytest.mark.asyncio
async def test_inventory_and_state_export_allowlist_redacts_token():
    client, api = fixture_client()
    row = api.rows["light.desk_led"]
    row["attributes"].update(
        friendly_name=api._token,
        access_token=api._token,
        private_url="http://private.invalid",
        password="do-not-export",
    )
    result = await client.get_state("light.desk_led")
    overview = await client.inventory()
    assert api._token not in repr(result) + repr(overview)
    assert "private.invalid" not in repr(result) + repr(overview)
    assert "do-not-export" not in repr(result)
    assert "entities" not in overview


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,code", [(401, "auth"), (403, "auth"), (404, "missing"), (500, "http")]
)
async def test_rest_transport_redacts_server_errors(monkeypatch, status, code):
    actual = httpx.AsyncClient
    transport = httpx.MockTransport(
        lambda req: httpx.Response(status, text="private-token-and-url")
    )
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kwargs: actual(transport=transport, **kwargs)
    )
    api = HomeAssistantAPI("http://fake.invalid", "private-token")
    with pytest.raises(HAError) as exc:
        await api.request(
            "POST", "/api/services/light/turn_on", {"entity_id": "light.test"}
        )
    assert exc.value.code == code
    assert "private-token" not in repr(exc.value.result())
    assert exc.value.uncertain == (status == 500)


@pytest.mark.asyncio
async def test_concurrent_commands_dispatch_once():
    import asyncio

    client, api = fixture_client()
    ctx = context(client)
    await asyncio.gather(
        client.control(ctx, "desk lights", "on"), client.control(ctx, "LEDs", "on")
    )
    assert len([e for e in api.events if e[0] == "POST"]) == 1


def test_domain_services_are_fixed_and_parameter_ranges_checked():
    for domain, action, service in [
        ("cover", "open", "open_cover"),
        ("climate", "temperature", "set_temperature"),
        ("media_player", "pause", "media_pause"),
    ]:
        row = {"attributes": {"min_temp": 5, "max_temp": 30}}
        assert service_plan({"domain": domain}, row, action, 22, "")[0] == service
    with pytest.raises(ValueError):
        service_plan({"domain": "switch"}, {}, "open", None, "")
    with pytest.raises(ValueError):
        service_plan({"domain": "media_player"}, {}, "volume", 101, "")
    assert not matches({"state": "off"}, {})


@pytest.mark.asyncio
async def test_entity_id_recycled_during_cache_is_not_controlled():
    client, api = fixture_client()
    await client.inventory()
    next(r for r in api.registry["entity"] if r["entity_id"] == "light.desk_led")[
        "id"
    ] = "replacement-device"
    result = await client.control(context(client), "Desk lights", "on")
    assert result["code"] == "stale_target"
    assert not any(e[0] == "POST" for e in api.events)


@pytest.mark.asyncio
async def test_unknown_area_does_not_select_unrelated_room_sensor():
    client, _ = fixture_client()
    result = await client.get_state("Office temperature")
    assert result["code"] == "not_found"


@pytest.mark.asyncio
async def test_alias_priority_and_removed_mapping_suggestions_not_dispatch():
    client, api = fixture_client()
    await client.alias("remember", "Desk lights", "Desk socket")
    assert (await client.find("Desk lights"))["entity"][
        "entity_id"
    ] == "switch.desk_socket"
    api.rows.pop("switch.desk_socket")
    client.refreshed = -float("inf")
    result = await client.control(context(client), "Desk lights", "on")
    assert result["code"] == "stale_alias"
    assert not any(e[0] == "POST" for e in api.events)


@pytest.mark.asyncio
async def test_new_user_turn_can_control_same_light_again_after_verified_change():
    client, api = fixture_client()
    ctx = context(client)
    await client.control(ctx, "Desk lights", "on")
    ctx.session.history.items.append(SimpleNamespace(role="user", id="u2"))
    await client.control(ctx, "LEDs", "off")
    ctx.session.history.items.append(SimpleNamespace(role="user", id="u3"))
    await client.control(ctx, "Desk lights", "on")
    assert len([e for e in api.events if e[0] == "POST"]) == 3


@pytest.mark.asyncio
async def test_post_transport_timeout_and_invalid_json_are_uncertain(monkeypatch):
    actual = httpx.AsyncClient
    for response in (
        httpx.ReadTimeout("private-token"),
        httpx.Response(200, text="not-json-private-token"),
    ):

        def handle(req, response=response):
            if isinstance(response, Exception):
                raise response
            return response

        monkeypatch.setattr(
            httpx,
            "AsyncClient",
            lambda **kwargs: actual(transport=httpx.MockTransport(handle), **kwargs),
        )
        with pytest.raises(HAError) as exc:
            await HomeAssistantAPI("http://fake.invalid", "private-token").request(
                "POST", "/api/services/light/turn_on", {}
            )
        assert exc.value.uncertain
        assert "private-token" not in repr(exc.value.result())


@pytest.mark.asyncio
async def test_response_size_is_bounded(monkeypatch):
    import home_assistant_api

    monkeypatch.setattr(home_assistant_api, "MAX_BYTES", 20)
    actual = httpx.AsyncClient
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json=["x" * 100]))
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kwargs: actual(transport=transport, **kwargs)
    )
    with pytest.raises(HAError, match="response"):
        await HomeAssistantAPI("http://fake.invalid", "token").request(
            "GET", "/api/states"
        )


@pytest.mark.asyncio
async def test_websocket_auth_and_registry_command_contract(monkeypatch):
    import home_assistant_api

    class FakeSocket:
        def __init__(self):
            self.sent = []
            self.replies = [
                {"type": "auth_required"},
                {"type": "auth_ok"},
                *[
                    {"id": i, "type": "result", "success": True, "result": []}
                    for i in (1, 2, 3)
                ],
            ]

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def receive_json(self):
            return self.replies.pop(0)

        async def send_json(self, data):
            self.sent.append(data)

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        def ws_connect(self, url, **kwargs):
            assert url == "wss://fake.invalid/api/websocket"
            assert kwargs["max_msg_size"] == home_assistant_api.MAX_BYTES
            return socket

    socket = FakeSocket()
    monkeypatch.setattr(home_assistant_api.aiohttp, "ClientSession", FakeSession)
    api = HomeAssistantAPI("https://fake.invalid", "fixture-token")
    assert await api.registries() == {"entity": [], "device": [], "area": []}
    assert socket.sent[0] == {"type": "auth", "access_token": "fixture-token"}
    assert [s["type"] for s in socket.sent[1:]] == [
        "config/entity_registry/list",
        "config/device_registry/list",
        "config/area_registry/list",
    ]
    socket = FakeSocket()
    socket.replies[1] = {"type": "auth_invalid", "message": "fixture-token"}
    with pytest.raises(HAError, match="auth") as exc:
        await api.registries()
    assert "fixture-token" not in repr(exc.value.result())


@pytest.mark.asyncio
async def test_fallback_preserved_but_uncertain_fallback_blocks_controls():
    client, api = fixture_client()
    original = api.request

    async def fallback(method, path, data=None):
        if path == "/api/conversation/process":
            return {"response": {"speech": {"plain": {"speech": "Scene activated."}}}}
        return await original(method, path, data)

    api.request = fallback
    ctx = context(client)
    preview = await home_assistant_request._func(ctx, "Activate the evening scene")
    assert preview["requires_confirmation"]
    ctx.session.history.items.append(SimpleNamespace(role="user", id="approval1"))
    result = await home_assistant_request._func(
        ctx, "Activate the evening scene", confirmed=True
    )
    assert result["speech"] == "Scene activated." and not result["verified"]
    ctx.session.history.items.append(SimpleNamespace(role="user", id="u2"))

    async def timeout(*args):
        raise HAError("timeout", True)

    api.request = timeout
    await home_assistant_request._func(ctx, "Activate the night scene")
    ctx.session.history.items.append(SimpleNamespace(role="user", id="approval2"))
    assert (
        await home_assistant_request._func(
            ctx, "Activate the night scene", confirmed=True
        )
    )["uncertain"]
    api.request = original
    result = await client.control(ctx, "Desk lights", "on")
    assert result["uncertain"]
    assert not any(e[0] == "POST" for e in api.events)


@pytest.mark.asyncio
async def test_alias_limits_corrections_and_corrupt_storage(tmp_path):
    store = AliasStore("http://fake.invalid", tmp_path / "aliases.sqlite3")
    target = {"kind": "area", "id": "a", "name": "Bedroom", "stable": True}
    for i in range(100):
        store.run("remember", f"alias {i}", target)
    store.run("remember", "alias 0", {**target, "name": "New room"})
    with pytest.raises(ValueError, match="limit"):
        store.run("remember", "extra", target)
    assert store.run("recall")["alias 0"]["name"] == "New room"


@pytest.mark.asyncio
async def test_cover_requires_exact_preview_later_turn_and_single_dispatch():
    client, api = fixture_client()
    api.rows["cover.test_blind"] = {
        "entity_id": "cover.test_blind",
        "state": "closed",
        "attributes": {"friendly_name": "Test blind"},
    }
    api.registry["entity"].append({"id": "blind", "entity_id": "cover.test_blind"})
    ctx = context(client)
    preview = await client.control(ctx, "Test blind", "open", confirmed=True)
    assert preview["requires_confirmation"]
    assert (await client.control(ctx, "Test blind", "open", confirmed=True))[
        "requires_confirmation"
    ]
    assert not any(e[0] == "POST" for e in api.events)
    ctx.session.history.items.append(SimpleNamespace(role="user", id="approval"))
    await client.control(ctx, "Test blind", "open", confirmed=True)
    await client.control(ctx, "Test blind", "open", confirmed=True)
    assert len([e for e in api.events if e[0] == "POST"]) == 1


@pytest.mark.asyncio
async def test_malformed_assist_success_is_uncertain_not_safe_to_repeat():
    client, api = fixture_client()
    ctx = context(client)

    async def malformed(*args):
        return {"response": {}}

    api.request = malformed
    await home_assistant_request._func(ctx, "Activate scene")
    ctx.session.history.items.append(SimpleNamespace(role="user", id="approval"))
    result = await home_assistant_request._func(ctx, "Activate scene", confirmed=True)
    assert result["uncertain"] and result["dispatched"]
    assert ledger_for(ctx).receipts[-1].status == "uncertain"
    again = await home_assistant_request._func(ctx, "Activate scene", confirmed=True)
    assert again["uncertain"]


@pytest.mark.asyncio
async def test_cancelled_service_keeps_uncertain_receipt_and_blocks_replay():
    import asyncio

    client, api = fixture_client()
    original = api.request

    async def cancelled(method, path, data=None):
        if method == "POST":
            api.events.append((method, path, data))
            raise asyncio.CancelledError()
        return await original(method, path, data)

    api.request = cancelled
    ctx = context(client)
    with pytest.raises(asyncio.CancelledError):
        await client.control(ctx, "Desk lights", "on")
    assert ledger_for(ctx).receipts[0].status == "uncertain"
    assert (await client.control(ctx, "LEDs", "on"))["uncertain"]
    assert len([e for e in api.events if e[0] == "POST"]) == 1


@pytest.mark.asyncio
async def test_all_simulations_block_ha_unless_fixture_explicit(monkeypatch):
    from unittest.mock import Mock

    import simulation_tools
    from agent import Assistant

    install = Mock()
    monkeypatch.setattr(simulation_tools, "mock_tools", install)
    for fixture in (None, "ha_lights"):
        ctx = SimpleNamespace(
            simulation_context=lambda fixture=fixture: SimpleNamespace(
                userdata=lambda fixture=fixture: {"fixture": fixture}
            )
        )
        session = SimpleNamespace(userdata={})
        simulation_tools.configure_simulation_tools(ctx, session, Assistant)
        mocks = install.call_args.args[1]
        assert "home_assistant_request" in mocks
        assert ("home_assistant_control" in mocks) == (fixture is None)
        assert ("_ha_client" in session.userdata) == (fixture == "ha_lights")


@pytest.mark.asyncio
async def test_real_sdk_tool_arguments_and_session_state():
    from unittest.mock import Mock

    from livekit.agents import RunContext
    from livekit.agents.llm.utils import prepare_function_arguments

    client, api = fixture_client()
    ctx = Mock(spec=RunContext)
    ctx.session = context(client).session
    args, kwargs = prepare_function_arguments(
        fnc=home_assistant_control,
        json_arguments={"target": "Desk lights", "action": "on"},
        call_ctx=ctx,
    )
    result = await home_assistant_control._func(*args, **kwargs)
    assert result["verified"]
    assert len([e for e in api.events if e[0] == "POST"]) == 1


@pytest.mark.asyncio
async def test_bounded_inventory_and_invalid_supported_features_are_not_exported():
    import home_assistant_index

    client, api = fixture_client()
    api.rows["light.desk_led"]["attributes"]["supported_features"] = api._token
    result = await client.find("Desk lights")
    assert result["entity"]["supported_features"] == 0
    assert api._token not in repr(result)
    original_limit = home_assistant_index.MAX_ENTITIES
    try:
        home_assistant_index.MAX_ENTITIES = 2
        client.refreshed = -float("inf")
        result = await client.inventory(True)
        assert result["truncated"] and result["entity_count"] == 2
    finally:
        home_assistant_index.MAX_ENTITIES = original_limit


@pytest.mark.asyncio
async def test_urls_keys_and_alias_credentials_are_redacted_or_rejected():
    client, api = fixture_client()
    key = "AIza" + "A" * 35
    api.rows["sensor.desk_temperature"]["attributes"]["friendly_name"] = "Sensor " + key
    api.rows["sensor.desk_temperature"]["state"] = "https://private.invalid/?key=secret"
    result = await client.get_state("sensor.desk_temperature")
    assert key not in repr(result) and "private.invalid" not in repr(result)
    with pytest.raises(ValueError, match="credentials"):
        await client.alias("remember", key, "Desk lights")
    assert not await client.mappings()


@pytest.mark.asyncio
async def test_lookup_never_supplies_cached_measurements_and_read_is_fresh():
    client, api = fixture_client()
    result = await client.find("my room", device_class="humidity")
    assert "state" not in result["entity"]
    assert all("state" not in row for row in result["candidates"])
    api.rows["sensor.desk_humidity"]["state"] = "49"
    result = await client.get_state("my room", device_class="humidity")
    assert result["state"] == "49"
    assert ("GET", "/api/states/sensor.desk_humidity", None) in api.events


@pytest.mark.asyncio
async def test_unregistered_name_change_blocks_control_and_noop_records_read():
    client, api = fixture_client()
    api.registry["entity"] = [
        r for r in api.registry["entity"] if r["entity_id"] != "light.desk_led"
    ]
    ctx = context(client)
    await client.inventory()
    api.rows["light.desk_led"]["attributes"]["friendly_name"] = "New device"
    result = await client.control(ctx, "Desk lights", "on")
    assert result["code"] == "stale_target"
    assert not any(e[0] == "POST" for e in api.events)
    api.rows["light.desk_led"]["attributes"]["friendly_name"] = "Desk lights"
    api.rows["light.desk_led"]["state"] = "on"
    result = await client.control(ctx, "Desk lights", "on")
    assert result["already_in_requested_state"] and not result["dispatched"]
    receipt = ledger_for(ctx).receipts[-1]
    assert receipt.status == "verified" and not receipt.write
