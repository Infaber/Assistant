"""Opt-in HA WebSocket transitions; reconnect baselines never become arrivals."""

import asyncio
import json
import os
import time
from collections import deque
from types import SimpleNamespace
from urllib.parse import urlsplit, urlunsplit

import aiohttp

from camera_awareness import timestamp
from frigate_api import enabled, identifier
from home_assistant import client_for
from home_assistant_api import MAX_BYTES, HAError, configuration
from home_assistant_index import normalized


class CameraTransitions:
    def __init__(self, cooldown=120, camera="bedroom"):
        self.camera = identifier(camera)
        self.states = {}
        self.seen = deque(maxlen=256)
        self.observed = {}
        self.last_spoken = -float("inf")
        self.cooldown = cooldown

    def reset(self):
        self.states.clear()
        self.seen.clear()
        self.observed.clear()

    def accept(self, entity, row, kind, now=None):
        now = time.time() if now is None else now
        if not isinstance(row, dict):
            return None
        observed = timestamp(row.get("last_updated"))
        if observed is None or not 0 <= now - observed <= 30:
            return None
        state = row.get("state")
        if not isinstance(state, str):
            return None
        event_id = (entity, observed, state)
        if event_id in self.seen or observed <= self.observed.get(
            entity, -float("inf")
        ):
            return None
        self.observed[entity] = observed
        self.seen.append(event_id)
        previous = self.states.get(entity)
        self.states[entity] = state
        if previous is None or previous == state:
            return None
        if kind == "person":
            try:
                before, after = float(previous), float(state)
                if (
                    not before.is_integer()
                    or not after.is_integer()
                    or not 0 <= before <= 100
                    or not 0 <= after <= 100
                ):
                    return None
            except ValueError:
                return None
            if before == 0 < after:
                return f"Someone was newly detected by the {self.camera} camera."
            if before > 0 == after:
                return f"The {self.camera} camera no longer detects a person."
        if kind == "availability":
            if previous not in {"unknown", "unavailable"} and state == "unavailable":
                return f"The {self.camera} camera entity is unavailable."
            if previous == "unavailable" and state not in {"unknown", "unavailable"}:
                return f"The {self.camera} camera entity is available again."
        if kind == "alert" and state.lower() == "alert" and previous.lower() != "alert":
            return f"There is a new {self.camera} camera alert."
        return None

    def can_speak(self, now, *, enabled, idle):
        if not enabled or not idle or now - self.last_spoken < self.cooldown:
            return False
        self.last_spoken = now
        return True


class CameraEventBridge:
    def __init__(self, companion, sources):
        self.companion = companion
        self.sources = sources
        self.speaking = False
        self.enabled = False  # Operator config never grants spoken announcements.
        self.transitions = CameraTransitions(
            camera=os.getenv("FRIGATE_CAMERA", "bedroom")
        )
        self.status = "connecting"

    async def run(self):
        delay = 2
        while (
            not self.companion.closed
            and enabled()
            and not getattr(self.companion, "closed_camera_events", False)
        ):
            try:
                await self.subscribe()
            except (
                aiohttp.ClientError,
                OSError,
                ValueError,
                TimeoutError,
                HAError,
                AttributeError,
                TypeError,
            ):
                self.status = "recovering"
            if self.companion.closed or getattr(
                self.companion, "closed_camera_events", False
            ):
                break
            await asyncio.sleep(delay)
            delay = 2 if self.status == "connected" else min(60, delay * 2)

    async def subscribe(self):
        url, token = configuration()
        p = urlsplit(url)
        websocket_url = urlunsplit(
            (
                "wss" if p.scheme == "https" else "ws",
                p.netloc,
                p.path + "/api/websocket",
                "",
                "",
            )
        )
        context = SimpleNamespace(session=self.companion.session)
        ha = client_for(context)
        index = await ha.refresh()
        for entity_id, kind in self.sources.items():
            entity = index.entities.get(entity_id)
            metadata = (
                normalized(
                    " ".join(
                        str(entity.get(k, "")) for k in ("name", "entity_id", "device")
                    )
                )
                if entity
                else ""
            )
            if (
                not entity
                or entity.get("platform") != "frigate"
                or not set(normalized(self.transitions.camera).split()).issubset(
                    metadata.split()
                )
            ):
                self.status = "invalid_source"
                self.companion.closed_camera_events = True
                return
            if kind == "person" and (
                "person" not in metadata.split()
                or "count" not in metadata.split()
                or "active" in metadata.split()
                or entity.get("unit") != "objects"
            ):
                self.status = "invalid_source"
                self.companion.closed_camera_events = True
                return
        self.transitions.reset()
        async with (
            aiohttp.ClientSession() as client,
            client.ws_connect(
                websocket_url, heartbeat=30, max_msg_size=MAX_BYTES
            ) as ws,
        ):
            if (await asyncio.wait_for(ws.receive_json(), 10)).get(
                "type"
            ) != "auth_required":
                raise ValueError("Invalid handshake")
            await ws.send_json({"type": "auth", "access_token": token})
            if (await asyncio.wait_for(ws.receive_json(), 10)).get("type") != "auth_ok":
                self.status = "authentication_required"
                # Exit without repeatedly retrying bad credentials.
                self.companion.closed_camera_events = True
                return
            await ws.send_json({"id": 1, "type": "get_states"})
            baseline = await asyncio.wait_for(ws.receive_json(), 10)
            if not baseline.get("success") or not isinstance(
                baseline.get("result"), list
            ):
                raise ValueError("Baseline unavailable")
            for row in baseline["result"]:
                if (
                    isinstance(row, dict)
                    and row.get("entity_id") in self.sources
                    and isinstance(row.get("state"), str)
                ):
                    self.transitions.states[row["entity_id"]] = row["state"]
                    if observed := timestamp(row.get("last_updated")):
                        self.transitions.observed[row["entity_id"]] = observed
            await ws.send_json(
                {"id": 2, "type": "subscribe_events", "event_type": "state_changed"}
            )
            result = await asyncio.wait_for(ws.receive_json(), 10)
            if not result.get("success"):
                raise ValueError("Subscription rejected")
            self.status = "connected"
            async for message in ws:
                if message.type != aiohttp.WSMsgType.TEXT:
                    continue
                frame = json.loads(message.data)
                if not isinstance(frame, dict) or frame.get("type") != "event":
                    continue
                event = frame.get("event", {})
                if (
                    not isinstance(event, dict)
                    or event.get("event_type") != "state_changed"
                ):
                    continue
                data = event.get("data", {})
                if not isinstance(data, dict):
                    continue
                entity = data.get("entity_id")
                if entity not in self.sources:
                    continue
                text = self.transitions.accept(
                    entity, data.get("new_state"), self.sources[entity]
                )
                if text and self.transitions.can_speak(
                    time.monotonic(), enabled=self.enabled, idle=self.idle()
                ):
                    await self.announce(text)

    def idle(self):
        c = self.companion
        return (
            c.session.agent_state == "listening"
            and c.session.user_state != "speaking"
            and time.monotonic() - c.policy.last_activity > 30
            and not c.uploads
            and c.speech is None
        )

    async def announce(self, text):
        c = self.companion
        try:
            self.speaking = True
            # Fixed text, not external UI instructions; no user-role message and no tools.
            c.speech = c.session.generate_reply(
                instructions="A permitted camera notification arrived. Say only: "
                + text
                + " Do not identify anyone, save memories, ask to control devices, or call tools.",
                tool_choice="none",
                tools=[],
                allow_interruptions=True,
            )
            await c.speech
        finally:
            self.speaking = False
            c.speech = None


def start_camera_events(companion):
    if (
        not enabled()
        or os.getenv("ARIANA_CAMERA_EVENTS_ENABLED", "false").lower() != "true"
    ):
        return None
    sources = {
        value: kind
        for variable, kind in (
            ("FRIGATE_HA_PERSON_ENTITY", "person"),
            ("FRIGATE_HA_CAMERA_ENTITY", "availability"),
            ("FRIGATE_HA_ALERT_ENTITY", "alert"),
        )
        if (value := os.getenv(variable, ""))
    }
    if not sources:
        return None
    bridge = CameraEventBridge(companion, sources)
    companion.spawn(bridge.run())
    return bridge
