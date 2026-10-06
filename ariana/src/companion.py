"""Room-scoped attachment receipts and opt-in, lease-bound proactive speech."""

import asyncio
import contextlib
import hashlib
import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from attachments import MAX_FILE_BYTES, MAX_FILES, MAX_SESSION_FILES, decode_attachment

logger = logging.getLogger(__name__)
ATTACHMENT_TOPIC = "ariana.attachments"
ATTACHMENT_METHOD = "ariana.attachments.commit"
CHECK_IN_METHOD = "ariana.check-ins"


@dataclass
class CheckInPolicy:
    enabled: bool = False
    interval: int = 15
    quiet_start: int = 22
    quiet_end: int = 8
    timezone: str = "Europe/Oslo"
    lease_until: float = 0
    last_activity: float = 0
    awaiting_user: bool = False

    def configure(self, payload: dict, now: float):
        if not isinstance(payload, dict):
            raise ValueError("Check-in settings must be an object.")
        if type(payload.get("enabled")) is not bool or payload.get("interval") not in {
            5,
            15,
            30,
            60,
        }:
            raise ValueError(
                "Choose check-ins on/off and an interval of 5, 15, 30 or 60 minutes."
            )
        for key in ("quiet_start", "quiet_end"):
            if type(payload.get(key)) is not int or not 0 <= payload[key] < 24:
                raise ValueError("Quiet hours must be whole hours from 0 to 23.")
        try:
            ZoneInfo(payload.get("timezone", ""))
        except (ValueError, TypeError, ZoneInfoNotFoundError) as error:
            raise ValueError("Choose a valid timezone.") from error
        changed = any(
            getattr(self, key) != payload[key]
            for key in ("enabled", "interval", "quiet_start", "quiet_end", "timezone")
        )
        for key in ("enabled", "interval", "quiet_start", "quiet_end", "timezone"):
            setattr(self, key, payload[key])
        self.lease_until = now + 90 if self.enabled else 0
        if changed:
            self.last_activity = now
        # Heartbeats and toggling never clear an unanswered check-in.

    def activity(self, now: float, *, user: bool = False):
        self.last_activity = now
        if user:
            self.awaiting_user = False

    def due(self, now: float, hour: int, *, idle: bool) -> bool:
        quiet = self.quiet_start != self.quiet_end and (
            self.quiet_start <= hour < self.quiet_end
            if self.quiet_start < self.quiet_end
            else hour >= self.quiet_start or hour < self.quiet_end
        )
        return (
            self.enabled
            and now < self.lease_until
            and idle
            and not quiet
            and not self.awaiting_user
            and now - self.last_activity >= self.interval * 60
        )


class CompanionBridge:
    def __init__(self, room, session):
        self.room, self.session = room, session
        self.policy = CheckInPolicy(last_activity=time.monotonic())
        self.uploads = {}
        self.receipts = {}
        self.total_files = 0
        self.context_chars = 0
        self.tasks = set()
        self.lock = asyncio.Lock()
        self.speech = None
        self.closed = False

    def authorized(self, identity):
        participant = self.room.remote_participants.get(identity)
        # The room permits exactly one frontend participant and one named agent.
        return participant is not None and identity.startswith("guest-")

    def start(self):
        self.room.register_byte_stream_handler(ATTACHMENT_TOPIC, self.receive)
        self.room.local_participant.register_rpc_method(ATTACHMENT_METHOD, self.commit)
        self.room.local_participant.register_rpc_method(CHECK_IN_METHOD, self.configure)
        self.session.on("conversation_item_added", self.on_message)
        self.session.on("user_state_changed", self.on_user_state)
        self.spawn(self.check_in_loop())

    def spawn(self, coroutine):
        task = asyncio.create_task(coroutine)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    def on_message(self, event):
        item = event.item
        self.policy.activity(
            time.monotonic(), user=getattr(item, "role", None) == "user"
        )

    def on_user_state(self, event):
        if event.new_state == "speaking":
            self.policy.activity(time.monotonic(), user=True)

    def prune(self):
        now = time.monotonic()
        for key, (_, created, future) in list(self.uploads.items()):
            if now - created > 120 and future.done():
                del self.uploads[key]

    def receive(self, reader, identity):
        self.prune()
        key = reader.info.stream_id
        if (
            not self.authorized(identity)
            or key in self.uploads
            or len(self.uploads) >= MAX_FILES
            or self.total_files >= MAX_SESSION_FILES
        ):
            reader.close()
            return
        future = asyncio.get_running_loop().create_future()
        self.uploads[key] = (identity, time.monotonic(), future)
        self.spawn(self.read_upload(reader, future))

    async def read_upload(self, reader, future):
        try:
            if reader.info.size is not None and reader.info.size > MAX_FILE_BYTES:
                raise ValueError("Each attachment must be at most 10 MB.")
            data = bytearray()
            async with asyncio.timeout(45):
                async for chunk in reader:
                    if len(data) + len(chunk) > MAX_FILE_BYTES:
                        raise ValueError("Each attachment must be at most 10 MB.")
                    data.extend(chunk)
                content = await asyncio.to_thread(
                    decode_attachment, reader.info.name, bytes(data)
                )
            future.set_result({"content": content})
        except asyncio.CancelledError:
            future.cancel()
            raise
        except Exception as error:
            future.set_result(
                {
                    "error": str(error)
                    if isinstance(error, ValueError)
                    else "Attachment transfer failed. Try again."
                }
            )
        finally:
            reader.close()

    async def commit(self, invocation):
        if not self.authorized(invocation.caller_identity):
            return json.dumps(
                {"error": "Only the connected user can share attachments."}
            )
        try:
            payload = json.loads(invocation.payload)
            ids, question, request_id = (
                payload["ids"],
                payload["question"],
                payload["request_id"],
            )
            if (
                not isinstance(ids, list)
                or not 1 <= len(ids) <= MAX_FILES
                or any(not isinstance(i, str) for i in ids)
                or len(set(ids)) != len(ids)
                or not isinstance(question, str)
                or len(question) > 4000
                or not isinstance(request_id, str)
                or not 1 <= len(request_id) <= 80
            ):
                raise ValueError("Send up to three attachments and a short message.")
            digest = hashlib.sha256(invocation.payload.encode()).hexdigest()
            async with self.lock:
                if request_id in self.receipts:
                    old_digest, receipt = self.receipts[request_id]
                    if old_digest != digest:
                        raise ValueError(
                            "This send ID was already used for a different message."
                        )
                    return receipt
                if self.total_files + len(ids) > MAX_SESSION_FILES:
                    raise ValueError(
                        "This conversation has reached its 20-file limit. Start a new conversation."
                    )
                entries = [self.uploads.get(key) for key in ids]
                if any(
                    entry is None or entry[0] != invocation.caller_identity
                    for entry in entries
                ):
                    raise ValueError(
                        "An attachment was not received or expired. Remove it and attach it again."
                    )
                results = await asyncio.wait_for(
                    asyncio.gather(*(asyncio.shield(entry[2]) for entry in entries)),
                    timeout=8,
                )
                if errors := [r["error"] for r in results if "error" in r]:
                    # A rejected batch must not fill the inbox and block replacements.
                    for key in ids:
                        del self.uploads[key]
                    raise ValueError(errors[0])
                content = [
                    question.strip()
                    or "Please describe or summarize the attachments I am sharing."
                ]
                for result in results:
                    content.extend(result["content"])
                added_chars = sum(
                    len(part) for part in content if isinstance(part, str)
                )
                if self.context_chars + added_chars > 80000:
                    raise ValueError(
                        "This conversation has reached its document text limit. Start a new conversation."
                    )
                # Realtime generate_reply(ChatMessage) drops images in SDK 1.8.
                # Use the documented multimodal chat-context update instead.
                agent = self.session.current_agent
                chat = agent.chat_ctx.copy()
                message_id = "attachment-" + request_id
                if chat.get_by_id(message_id) is None:
                    chat.add_message(role="user", content=content, id=message_id)
                await agent.update_chat_ctx(chat)
                self.session.generate_reply()
                self.policy.activity(time.monotonic(), user=True)
                receipt = json.dumps({"accepted": True, "request_id": request_id})
                self.receipts[request_id] = (digest, receipt)
                self.total_files += len(ids)
                self.context_chars += added_chars
                for key in ids:
                    del self.uploads[key]
                return receipt
        except (KeyError, TypeError, ValueError, TimeoutError) as error:
            return json.dumps(
                {
                    "error": str(error)
                    if isinstance(error, ValueError)
                    else "Attachments are still arriving. Retry sending; they will not be sent twice."
                }
            )
        except Exception:
            logger.exception("Attachment submission failed")
            return json.dumps(
                {
                    "error": "Ariana could not accept this message. Check the connection before retrying."
                }
            )

    async def configure(self, invocation):
        if not self.authorized(invocation.caller_identity):
            return json.dumps(
                {"error": "Only the connected user can change check-ins."}
            )
        try:
            self.policy.configure(json.loads(invocation.payload), time.monotonic())
            if not self.policy.enabled and self.speech is not None:
                self.speech.interrupt()
            return json.dumps(
                {
                    "enabled": self.policy.enabled,
                    "awaiting_user": self.policy.awaiting_user,
                    "idle_seconds": int(time.monotonic() - self.policy.last_activity),
                    "agent_state": self.session.agent_state,
                    "user_state": self.session.user_state,
                }
            )
        except (TypeError, ValueError, KeyError) as error:
            return json.dumps({"error": str(error)})

    async def check_in_loop(self):
        while not self.closed:
            await asyncio.sleep(5)
            self.prune()
            hour = datetime.now(ZoneInfo(self.policy.timezone)).hour
            idle = (
                self.session.agent_state == "listening"
                and self.session.user_state != "speaking"
                and not self.uploads
            )
            if not self.policy.due(time.monotonic(), hour, idle=idle):
                continue
            # One unanswered check-in maximum. Never run tools or inspect private apps.
            self.policy.awaiting_user = True
            self.policy.activity(time.monotonic())
            try:
                self.speech = self.session.generate_reply(
                    instructions="The user enabled optional proactive check-ins. Start a brief, natural conversation in one or two sentences, using relevant interests or the current conversation if helpful. Ask one gentle question. Do not claim an event, deadline, location or activity you have not verified. Do not access apps, create notes, save memory, or take any action. This is a check-in, not a new user request.",
                    tool_choice="none",
                    allow_interruptions=True,
                )
                await self.speech
            except Exception:
                logger.exception("Proactive check-in failed")
            finally:
                self.speech = None

    async def close(self):
        self.closed = True
        self.policy.enabled = False
        self.room.unregister_byte_stream_handler(ATTACHMENT_TOPIC)
        self.room.local_participant.unregister_rpc_method(ATTACHMENT_METHOD)
        self.room.local_participant.unregister_rpc_method(CHECK_IN_METHOD)
        self.session.off("conversation_item_added", self.on_message)
        self.session.off("user_state_changed", self.on_user_state)
        if self.speech is not None:
            with contextlib.suppress(Exception):
                self.speech.interrupt()
        tasks = list(self.tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.uploads.clear()
        self.receipts.clear()
