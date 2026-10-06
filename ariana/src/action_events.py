"""Small, redacted action events shared with the connected frontend."""

import asyncio
import functools
import inspect
import json
import time
from contextlib import suppress
from uuid import uuid4

TOPIC = "ariana.activity"


def result_state(result):
    if isinstance(result, dict):
        if result.get("uncertain"):
            return "uncertain", "The result needs checking before another action."
        if result.get("error"):
            return (
                "failed",
                "The tool could not complete this request. Ariana has the details.",
            )
        if result.get("preview") or result.get("requires_confirmation"):
            return "approval", "Waiting for your approval."
        if result.get("verified"):
            return "verified", "The result was checked."
        if result.get("read_unavailable"):
            return (
                "uncertain",
                "The page opened, but its contents could not be verified.",
            )
    # Legacy tools return plain text. Do not convert an arbitrary string into success.
    return "returned", "A result was returned; see Ariana's response."


async def emit(context, event):
    try:
        state = context.session.userdata
        sender = state.get("_activity_sender")
        if sender:
            await sender({"version": 1, "timestamp": time.time(), **event})
    except (AttributeError, ValueError, TypeError):
        pass


def observed(label):
    """Wrap before @function_tool to preserve its normal signature and validation."""

    def decorate(function):
        signature = inspect.signature(function)

        @functools.wraps(function)
        async def run(*args, **kwargs):
            context = signature.bind_partial(*args, **kwargs).arguments.get("context")
            event = {"id": uuid4().hex, "label": label, "kind": "action"}
            await emit(
                context,
                {**event, "status": "running", "detail": "Working on your request."},
            )
            try:
                result = await function(*args, **kwargs)
            except asyncio.CancelledError:
                await emit(
                    context,
                    {
                        **event,
                        "status": "uncertain",
                        "detail": "Interrupted. An in-flight action may still have completed.",
                    },
                )
                raise
            except Exception:
                await emit(
                    context,
                    {
                        **event,
                        "status": "failed",
                        "detail": "The tool could not complete this request.",
                    },
                )
                raise
            status, detail = result_state(result)
            await emit(context, {**event, "status": status, "detail": detail})
            return result

        return run

    return decorate


class ActivityPublisher:
    def __init__(self, room):
        self.room = room
        self.tasks = set()

    async def send(self, event):
        # UI feedback must never break or replay a real-world operation.
        with suppress(Exception):
            await asyncio.wait_for(
                self.room.local_participant.publish_data(
                    json.dumps(event).encode(), reliable=True, topic=TOPIC
                ),
                timeout=1,
            )

    async def enqueue(self, event):
        self.publish(event)

    def publish(self, event):
        task = asyncio.create_task(
            self.send({"version": 1, "timestamp": time.time(), **event})
        )
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def close(self):
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
