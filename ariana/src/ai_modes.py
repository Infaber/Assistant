"""Authenticated UI mode handoffs. Models and untrusted content cannot invoke this RPC."""

import asyncio
import json
import os
from contextlib import suppress

from model_config import configured_model

MODE_RPC = "ariana.mode"
MODES = {"normal", "local"}


def initial_mode(metadata=""):
    try:
        mode = (
            json.loads(metadata).get("mode", "normal")
            if metadata
            else os.getenv("ARIANA_MODE", "normal")
        )
    except (ValueError, AttributeError, TypeError):
        mode = "normal"
    return mode if mode in MODES else "normal"


def action_running(session):
    ledger = session.userdata.get("_task_ledger")
    return bool(ledger and any(item.status == "running" for item in ledger.receipts))


class ModeBridge:
    def __init__(self, room, session, make_agent, mode="normal", prepare=None):
        self.room, self.session, self.make_agent = room, session, make_agent
        self.mode, self.state = mode, "connecting"
        self.lock = asyncio.Lock()
        self.ready = None
        self.prepare = prepare
        self.error = ""
        self.context_transferred = False
        self.tasks = set()
        self.registered = False

    def status(self):
        from local_config import local_model

        model = local_model() if self.mode == "local" else configured_model()
        with suppress(AttributeError, RuntimeError):
            current = self.session.current_agent
            if getattr(current, "ai_mode", self.mode) == self.mode:
                model = current.llm.model
        return {
            "mode": self.mode,
            "state": self.state,
            "model": model,
            "error": self.error,
            "context_transferred": self.context_transferred,
        }

    async def publish(self):
        data = self.status()
        await self.room.local_participant.set_attributes(
            {
                f"ariana.{key}": str(data[key])
                for key in ("mode", "state", "model", "error")
            }
        )

    async def entered(self, mode):
        self.start()
        self.mode, self.state, self.error = mode, "ready", ""
        self.session.userdata["_ai_mode"] = mode
        await self.publish()
        if self.ready is not None and not self.ready.done():
            self.ready.set_result(True)

    async def switch(self, target, *, carry_context=False):
        if type(carry_context) is not bool:
            return {"error": "Conversation transfer must be explicitly on or off."}
        if target not in MODES:
            return {"error": "Choose Normal or Unrestricted Mode."}
        if self.lock.locked():
            return {"error": "A mode change is already in progress."}
        async with self.lock:
            if target == self.mode and self.state == "ready":
                return self.status()
            # Gate new effectful calls before inspecting in-flight receipts.
            self.session.userdata["_mode_switching"] = True
            try:
                from camera_delivery import delivery_pending

                companion = self.session.userdata.get("_companion_bridge")
                if companion and (
                    companion.lock.locked()
                    or any(not item[2].done() for item in companion.uploads.values())
                ):
                    return {
                        "error": "An attachment is still being processed. Finish or cancel that transfer before switching."
                    }
                if action_running(self.session) or delivery_pending(self.session):
                    return {
                        "error": "An action or image analysis is still running. Check its outcome before switching."
                    }
                self.state, self.error = "loading", ""
                await self.publish()
                if target == "local":
                    if self.prepare is None:
                        from local_models import prepare_local

                        await prepare_local()
                    else:
                        await self.prepare()
                # No model change until all target dependencies are prepared.
                await self.session.interrupt()
                if carry_context:
                    from conversation_context import transfer_context

                    chat = transfer_context(self.session.current_agent.chat_ctx)
                    agent = self.make_agent(target, self.entered, chat)
                    transferred = bool(chat.items)
                else:
                    agent = self.make_agent(target, self.entered)
                    transferred = False
                if companion:
                    companion.uploads.clear()
                for key in (
                    "notes_pending",
                    "mac_snapshot",
                    "_camera_consent",
                    "_ha_fallback_turn",
                ):
                    self.session.userdata.pop(key, None)
                self.ready = asyncio.get_running_loop().create_future()
                self.context_transferred = transferred
                self.session.update_agent(agent)
                await asyncio.wait_for(asyncio.shield(self.ready), 30)
                return self.status()
            except Exception:
                self.state = "error"
                self.error = "Mode change did not complete. Check local model setup or explicitly choose Normal Mode; no automatic cloud fallback occurred."
                await self.publish()
                return {**self.status(), "error": self.error}
            finally:
                if self.state == "loading":
                    self.state = (
                        "ready"  # A blocked action left the existing pipeline intact.
                    )
                self.session.userdata["_mode_switching"] = False

    def fail_local(self, detail):
        self.state, self.error = "error", detail
        task = asyncio.create_task(self.publish())
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def rpc(self, invocation):
        participant = self.room.remote_participants.get(invocation.caller_identity)
        if participant is None or not invocation.caller_identity.startswith("guest-"):
            return json.dumps(
                {"error": "Only the connected user can select an AI mode."}
            )
        try:
            request = json.loads(invocation.payload)
            if request.get("action") == "status":
                return json.dumps(self.status())
            if request.get("action") != "switch":
                raise ValueError
            return json.dumps(
                await self.switch(
                    request.get("mode"),
                    carry_context=request.get("carry_context", False),
                )
            )
        except (ValueError, TypeError, AttributeError):
            return json.dumps({"error": "Invalid mode request."})

    def start(self):
        if not self.registered:
            self.room.local_participant.register_rpc_method(MODE_RPC, self.rpc)
            self.registered = True

    async def close(self):
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        if self.registered:
            self.room.local_participant.unregister_rpc_method(MODE_RPC)
