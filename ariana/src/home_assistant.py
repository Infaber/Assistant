"""Discovery, fresh reads and guarded one-target Home Assistant effects."""

import asyncio
import time
from contextlib import suppress
from uuid import uuid4

from action_events import emit
from home_assistant_aliases import AliasStore
from home_assistant_api import HAError, HomeAssistantAPI, configuration
from home_assistant_index import Inventory, normalized
from notes_tools import write_approval
from task_ledger import action_fingerprint, ledger_for

CACHE_SECONDS = 600
SERVICES = {
    "light": {"on": "turn_on", "off": "turn_off", "brightness": "turn_on"},
    "switch": {"on": "turn_on", "off": "turn_off"},
    "cover": {"open": "open_cover", "close": "close_cover", "stop": "stop_cover"},
    "climate": {
        "on": "turn_on",
        "off": "turn_off",
        "temperature": "set_temperature",
        "mode": "set_hvac_mode",
    },
    "media_player": {
        "on": "turn_on",
        "off": "turn_off",
        "play": "media_play",
        "pause": "media_pause",
        "volume": "volume_set",
    },
    "fan": {"on": "turn_on", "off": "turn_off"},
}


def user_turn(context):
    try:
        return next(
            item.id
            for item in reversed(context.session.history.items)
            if getattr(item, "role", None) == "user"
        )
    except (AttributeError, StopIteration):
        return ""


class HomeAssistant:
    def __init__(self, api, aliases=None, clock=time.monotonic):
        self.api = api
        self.aliases = aliases or AliasStore(api.url)
        self.clock = clock
        self.index = None
        self.refreshed = -float("inf")
        self.attempted = -float("inf")
        self.last_error = None
        self.warning = None
        self.lock = asyncio.Lock()
        self.control_lock = asyncio.Lock()
        self.pending = {}

    async def refresh(self, force=False):
        async with self.lock:
            now = self.clock()
            if self.index and not force and now - self.refreshed < CACHE_SECONDS:
                return self.index
            if now - self.attempted < (2 if self.index else 30) and self.last_error:
                raise self.last_error
            if force and self.index and now - self.refreshed < 2:
                return self.index
            self.attempted = now
            try:
                states = await self.api.request("GET", "/api/states")
                if not isinstance(states, list):
                    raise HAError("response")
                try:
                    registries = await self.api.registries()
                    self.warning = None
                except HAError as error:
                    if error.code == "auth":
                        raise
                    registries = {}
                    self.warning = error.result()["error"]
                index = Inventory(states, registries, self.api.safe_text)
                self.index = index
                self.refreshed = now
                self.last_error = None
                return index
            except HAError as error:
                self.last_error = error
                raise

    async def mappings(self):
        return await asyncio.to_thread(self.aliases.run, "recall")

    async def find(self, query, domain="", device_class="", force=False):
        index = await self.refresh(force)
        aliases = await self.mappings()
        result = index.find(query, aliases, domain, device_class)
        if result.get("code") in {"not_found", "stale_alias"} and not force:
            index = await self.refresh(True)
            result = index.find(query, aliases, domain, device_class)
        if result.get("code") == "stale_alias":
            mapping = next(
                (v for a, v in aliases.items() if a == result.get("alias")), {}
            )
            # Suggestions only: a new identity never silently replaces a saved target.
            result["suggestions"] = index.find(
                mapping.get("name", query), {}, domain, device_class
            ).get("candidates", [])
        if self.warning:
            result["warning"] = self.warning
        if index.truncated:
            result["inventory_truncated"] = True
        return result

    async def resolve(self, query, domain="", device_class=""):
        result = await self.find(query, domain, device_class)
        if result.get("status") != "resolved":
            return None, result
        return self.index.entities[result["entity"]["entity_id"]], result

    async def raw_state(self, entity):
        row = await self.api.request("GET", "/api/states/" + entity["entity_id"])
        if (
            not isinstance(row, dict)
            or row.get("entity_id") != entity["entity_id"]
            or not isinstance(row.get("attributes", {}), dict)
        ):
            raise HAError("response")
        return row

    def state_result(self, entity, row):
        attrs = row.get("attributes", {})
        state = row.get("state")
        available = state not in {None, "unknown", "unavailable"}
        result = {
            "entity_id": entity["entity_id"],
            "name": self.api.safe_text(attrs.get("friendly_name") or entity["name"]),
            "area": entity["area"],
            "state": self.api.safe_text(state),
            "unit": self.api.safe_text(
                attrs.get("unit_of_measurement") or entity["unit"]
            ),
            "available": available,
            "verified": available,
        }
        if not available:
            result.update(
                error="This entity is unavailable or has no known state.",
                code="unavailable",
                verified=False,
            )
        return result

    async def get_state(self, query, domain="", device_class=""):
        entity, result = await self.resolve(query, domain, device_class)
        if not entity:
            return result
        try:
            row = await self.raw_state(entity)
        except HAError as error:
            if error.code == "missing":
                await self.refresh(True)
            raise
        result = self.state_result(entity, row)
        pending = self.pending.get(entity.get("registry_id") or entity["entity_id"])
        if (
            pending
            and pending["receipt"].status != "running"
            and matches(row, pending["expected"])
        ):
            pending["receipt"].status = "verified"
            result["verified_action_id"] = pending["receipt"].id
            self.pending.pop(entity.get("registry_id") or entity["entity_id"], None)
        return result

    async def inventory(self, force=False):
        index = await self.refresh(force)
        # Metadata overview, never the raw state database.
        counts = {}
        for row in index.entities.values():
            counts[row["domain"]] = counts.get(row["domain"], 0) + 1
        return {
            "entity_count": len(index.entities),
            "domains": counts,
            "areas": [
                {"id": self.api.safe_text(a["id"]), "name": a["name"]}
                for a in list(index.areas.values())[:30]
            ],
            "area_count": len(index.areas),
            "truncated": index.truncated or len(index.areas) > 30,
            "warning": self.warning,
            "next": "Use home_assistant_find for a specific device/sensor; get_state always reads fresh state.",
        }

    async def alias(self, action, alias="", target="", kind="entity"):
        if action == "remember" and self.api.safe_text(alias, 1000) != alias:
            raise ValueError(
                "Do not store credentials or URLs in Home Assistant aliases."
            )
        alias = normalized(alias)
        if action == "remember":
            index = await self.refresh()
            if kind == "entity":
                # Ignore old mappings so users can repair an obsolete alias.
                result = index.find(target)
                if result.get("status") != "resolved":
                    return result
                row = index.entities[result["entity"]["entity_id"]]
            else:
                source = index.areas if kind == "area" else index.devices
                rows = [
                    r
                    for r in source.values()
                    if normalized(target) == normalized(r["name"]) or target == r["id"]
                ]
                if len(rows) != 1:
                    return {
                        "status": "ambiguous" if rows else "not_found",
                        "candidates": [
                            {"id": r["id"], "name": r["name"]} for r in rows[:8]
                        ],
                        "message": "Choose the exact area/device before saving its alias.",
                    }
                row = rows[0]
            mapping = index.stable_target(kind, row)
            await asyncio.to_thread(self.aliases.run, action, alias, mapping)
            return {"saved": True, "alias": alias, "kind": kind, "target": row["name"]}
        data = await asyncio.to_thread(self.aliases.run, action, alias)
        return {
            "aliases": [
                {"alias": a, "kind": m["kind"], "target": m["name"]}
                for a, m in data.items()
            ][:20],
            "alias_count": len(data),
            "forgotten": action == "forget",
        }

    async def control(
        self, context, target, action, value=None, mode="", confirmed=False
    ):
        # Serialize resolution/read/dispatch/receipt to close concurrent duplicate races.
        async with self.control_lock:
            entity, result = await self.resolve(target)
            if not entity:
                return result
            eid = entity["entity_id"]
            context.session.userdata["_ha_resolved_turn"] = user_turn(context)
            ledger = ledger_for(context)
            if ledger is None or not user_turn(context):
                return {
                    "error": "An active user conversation is required for Home Assistant control."
                }
            target_key = entity.get("registry_id") or eid
            pending = self.pending.get(target_key)
            if pending or any(
                r.write
                and r.label == "Home Assistant fallback"
                and r.status in {"running", "uncertain"}
                for r in ledger.receipts
            ):
                return {
                    "error": "A previous Home Assistant action is still unverified. Read its state before considering another action; do not send a duplicate or Assist fallback.",
                    "uncertain": True,
                }
            try:
                if entity.get("registry_id"):
                    identity = await self.api.registry_entity(eid)
                    if (
                        identity.get("id") != entity["registry_id"]
                        or identity.get("disabled_by")
                        or identity.get("hidden_by")
                    ):
                        await self.refresh(True)
                        return {
                            "error": "The target's registry identity changed. Resolve it again; no service was dispatched.",
                            "code": "stale_target",
                        }
                row = await self.raw_state(entity)
            except HAError as error:
                if error.code == "missing":
                    await self.refresh(True)
                raise
            if (
                not entity.get("registry_id")
                and self.api.safe_text(
                    row.get("attributes", {}).get("friendly_name") or eid
                )
                != entity["name"]
            ):
                await self.refresh(True)
                return {
                    "error": "The unregistered target's name changed. Resolve it again before controlling it.",
                    "code": "stale_target",
                }
            if row.get("state") in {"unknown", "unavailable", None}:
                return {
                    "error": "This entity is unavailable; no service was dispatched.",
                    "code": "unavailable",
                }
            service, data, expected = service_plan(entity, row, action, value, mode)
            if entity["domain"] == "cover" and action in {"open", "close"}:
                preview = write_approval(
                    context,
                    "Home Assistant cover movement",
                    {"entity_id": eid, "action": action},
                    confirmed,
                )
                if preview:
                    return {"requires_confirmation": True, "preview": preview}
            if expected and matches(row, expected):
                check = ledger.begin(
                    uuid4().hex,
                    "Home Assistant state check",
                    action_fingerprint(
                        "home_assistant_state",
                        {"target_identity": target_key, "expected": expected},
                    ),
                    False,
                )
                check.status = "verified"
                await emit(
                    context,
                    {
                        "id": check.id,
                        "label": check.label,
                        "kind": "action",
                        "status": "verified",
                        "detail": "The device is already in the requested state; no command was sent.",
                    },
                )
                return {
                    **self.state_result(entity, row),
                    "already_in_requested_state": True,
                    "dispatched": False,
                }
            fingerprint = action_fingerprint(
                "home_assistant_service",
                {
                    "target_identity": target_key,
                    "service": service,
                    "data": data,
                    "user_turn": user_turn(context),
                },
            )
            previous = ledger.previous_write(fingerprint)
            if previous:
                return {
                    "error": "This resolved service was already dispatched for this user request. Read its state; do not repeat it.",
                    "uncertain": previous.status != "verified",
                    "action_id": previous.id,
                }
            receipt = ledger.begin(
                uuid4().hex, "Home Assistant control", fingerprint, True
            )
            event = {"id": receipt.id, "label": receipt.label, "kind": "action"}
            self.pending[target_key] = {"receipt": receipt, "expected": expected}
            await emit(
                context,
                {
                    **event,
                    "status": "running",
                    "detail": "Sending one resolved device service.",
                },
            )
            try:
                await self.api.request(
                    "POST",
                    f"/api/services/{entity['domain']}/{service}",
                    {"entity_id": eid, **data},
                )
                receipt.status = "returned"
                try:
                    after = await self.raw_state(entity)
                    verified = bool(expected) and matches(after, expected)
                    result = {
                        **self.state_result(entity, after),
                        "verified": verified,
                        "dispatched": True,
                    }
                    if verified:
                        receipt.status = "verified"
                        self.pending.pop(target_key, None)
                    else:
                        result["message"] = (
                            "Service returned, but the requested outcome is not yet verified. Read state again; do not resend the command."
                        )
                except HAError:
                    receipt.status = "uncertain"
                    result = {
                        "error": "The service was dispatched, but its resulting state could not be read. Check state before retrying.",
                        "uncertain": True,
                        "dispatched": True,
                    }
            except HAError as error:
                result = error.result()
                receipt.status = "uncertain" if error.uncertain else "failed"
                if error.uncertain:
                    # Observation is read-only; it never retries the service.
                    with suppress(HAError):
                        result["observed_state"] = self.state_result(
                            entity, await self.raw_state(entity)
                        )
                else:
                    self.pending.pop(target_key, None)
                    if error.code == "missing":
                        await self.refresh(True)
            except (asyncio.CancelledError, Exception):
                receipt.status = "uncertain"
                await emit(
                    context,
                    {
                        **event,
                        "status": "uncertain",
                        "detail": "Interrupted; the device command may already have completed. Read state before another command.",
                    },
                )
                raise
            await emit(
                context,
                {
                    **event,
                    "status": receipt.status,
                    "detail": "Device state was checked."
                    if receipt.status == "verified"
                    else "Inspect the device state before another command.",
                },
            )
            return {"action_id": receipt.id, **result}


def service_plan(entity, row, action, value, mode):
    domain = entity["domain"]
    service = SERVICES.get(domain, {}).get(action)
    if not service:
        raise ValueError(
            "That action is not supported for this resolved domain. No service was dispatched."
        )
    data, expected = {}, {}
    attrs = row.get("attributes", {})
    if action in {"on", "off"}:
        expected = (
            {"state": action}
            if domain in {"light", "switch", "fan"} or action == "off"
            else {"state_not": ["off", "unknown", "unavailable"]}
        )
    if action == "brightness":
        if value is None or not 0 <= value <= 100 or "brightness" not in attrs:
            raise ValueError(
                "Brightness requires a supported light and a percentage from 0 to 100."
            )
        data = {"brightness_pct": value}
        expected = (
            {"state": "off"}
            if value == 0
            else {"state": "on", "brightness": round(value * 255 / 100)}
        )
    if action == "temperature":
        if value is None or not attrs.get("min_temp", 7) <= value <= attrs.get(
            "max_temp", 35
        ):
            raise ValueError(
                "Choose a set temperature within this climate entity's limits."
            )
        data, expected = {"temperature": value}, {"temperature": value}
    if action == "mode":
        if not mode or mode not in attrs.get("hvac_modes", []):
            raise ValueError("Choose a supported HVAC mode for this climate entity.")
        data, expected = {"hvac_mode": mode}, {"state": mode}
    if action in {"open", "close"}:
        expected = {"state": "open" if action == "open" else "closed"}
    if action in {"play", "pause"}:
        expected = {"state": "playing" if action == "play" else "paused"}
    if action == "stop":
        expected = {"state_not": ["opening", "closing", "unknown", "unavailable"]}
    if action == "volume":
        if value is None or not 0 <= value <= 100:
            raise ValueError("Volume must be a percentage from 0 to 100.")
        data, expected = {"volume_level": value / 100}, {"volume_level": value / 100}
    return service, data, expected


def matches(row, expected):
    if not expected:
        return False
    for key, value in expected.items():
        actual = (
            row.get("state") if key == "state" else row.get("attributes", {}).get(key)
        )
        if isinstance(value, (int, float)):
            if not isinstance(actual, (int, float)) or abs(actual - value) > (
                2 if key == "brightness" else 0.01
            ):
                return False
        elif actual != value:
            return False
    return True


def client_for(context):
    state = context.session.userdata
    if "_ha_client" in state:
        return state["_ha_client"]
    url, token = configuration()
    client = HomeAssistant(HomeAssistantAPI(url, token))
    state["_ha_client"] = client
    return client
