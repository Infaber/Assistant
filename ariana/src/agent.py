import asyncio
import logging
import os
import sqlite3
from pathlib import Path

from dotenv import load_dotenv
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    JobContext,
    TurnHandlingOptions,
    cli,
    room_io,
)
from livekit.plugins import ai_coustics

from action_events import ActivityPublisher
from ai_modes import ModeBridge, initial_mode
from browser_tools import BrowserToolset
from camera_tools import camera_announcements, camera_snapshot, camera_status
from companion import CompanionBridge
from conversation_context import local_context, retrieval_query
from conversation_tools import conversation_standby
from home_assistant_tools import (
    home_assistant_alias,
    home_assistant_control,
    home_assistant_find,
    home_assistant_get_state,
    home_assistant_inventory,
    home_assistant_room_context,
)
from instructions import configured_instructions
from local_tools import ai_engine_status
from mac_tools import mac_control
from memory_tools import MemoryStore, memory_context, memory_manage
from model_config import configured_voice, realtime_model
from notes_tools import notes_edit, notes_list, notes_read
from performance import for_session, install_performance
from preferences_tools import preferences_manage
from recovery import install_recovery
from simulation_tools import check_simulation_state, configure_simulation_tools
from spotify_tools import spotify_control
from status_tools import assistant_status
from task_ledger import task_status
from tools import (
    calendar_create_event,
    calendar_today,
    home_assistant_request,
    mail_send,
    mail_unread,
    notes_create,
    reminders_create,
    reminders_today,
    search_web,
    weather_forecast,
)
from voice_controls import VoiceControls

# LiveKit registers plugins on the importing main thread, before job threads run.
# Optional speech dependencies must not make Normal mode require the local extra.
try:
    import onnxruntime

    onnxruntime.disable_telemetry_events()
    __import__("livekit.plugins.openai")
    __import__("livekit.plugins.silero")
except ImportError:
    pass

logger = logging.getLogger("agent")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env.local")


def _google_api_key() -> str:
    for name in ("GOOGLE_API_KEY", "GEMINI_API_KEY"):
        if key := os.environ.get(name, "").strip():
            return key
    raise ValueError(
        "Set GOOGLE_API_KEY (or GEMINI_API_KEY) in .env.local or the environment."
    )


class Assistant(Agent):
    def __init__(
        self,
        saved_context: str = "",
        model_name: str = "",
        chat_ctx=None,
        browser=None,
        mode="normal",
        on_ready=None,
    ) -> None:
        self.voice_name = configured_voice() if mode == "normal" else "af_heart"
        self.ai_mode = mode
        self.on_ready = on_ready
        if mode == "local":
            from local_models import local_options

            options = local_options()
        else:
            options = {
                "llm": realtime_model(_google_api_key(), model_name),
                "turn_handling": TurnHandlingOptions(turn_detection="realtime_llm"),
            }
        tools = [
            search_web,
            camera_status,
            camera_snapshot,
            camera_announcements,
            home_assistant_request,
            home_assistant_inventory,
            home_assistant_room_context,
            home_assistant_find,
            home_assistant_get_state,
            home_assistant_control,
            home_assistant_alias,
            weather_forecast,
            calendar_today,
            calendar_create_event,
            reminders_today,
            reminders_create,
            mail_unread,
            mail_send,
            notes_create,
            notes_list,
            notes_read,
            notes_edit,
            mac_control,
            spotify_control,
            preferences_manage,
            memory_manage,
            conversation_standby,
            assistant_status,
            task_status,
            ai_engine_status,
            browser or BrowserToolset(),
        ]
        if mode == "local":
            tools = [tool for tool in tools if tool is not camera_snapshot]
        self._local_route = None
        super().__init__(
            chat_ctx=chat_ctx,
            **options,
            tools=tools,
            instructions=configured_instructions(mode)
            + saved_context
            + (
                "\nActive engine: local Ollama. Discuss controversial, mature, fictional and analytical topics directly without needless moralizing. Be accurate; do not invent facts. Conversational openness never changes action permissions. Relevant app tools are selected locally before each turn. Use the provided tools for actions, then report actual verified results. Never stop at saying you will check. Start with a short useful sentence. Usually answer in one or two sentences unless more detail is requested or needed for accuracy/approval. Reply in spoken US English without markdown or emojis; don't append 'let me know if' offers to simple acknowledgements. No vision support: do not claim to see images or screens."
                if mode == "local"
                else ""
            ),
        )

    async def llm_node(self, chat_ctx, tools, model_settings):
        if self.ai_mode == "local":
            from local_routing import choose_group, visible_tools

            users = [
                item for item in chat_ctx.items if getattr(item, "role", None) == "user"
            ]
            turn = users[-1].id if users else ""
            if self._local_route is None or self._local_route[0] != turn:
                excerpts = [
                    {"role": item.role, "text": item.text_content[:1200]}
                    for item in chat_ctx.items
                    if getattr(item, "role", None) in {"user", "assistant"}
                ][-6:]
                with for_session(self.session).measure("local_router"):
                    self._local_route = (turn, await choose_group(excerpts))
            tools = visible_tools(tools, self._local_route[1])
            backend = (
                self.session.userdata.get("_memory_simulator") or MemoryStore().run
            )
            try:
                recalled = await asyncio.to_thread(
                    backend, {"action": "recall", "query": retrieval_query(chat_ctx)}
                )
                memories = (
                    recalled.get("memories", [])[:6]
                    if retrieval_query(chat_ctx)
                    else []
                )
            except (OSError, ValueError, sqlite3.Error):
                memories = []
            chat_ctx = local_context(chat_ctx, memories)
        async for chunk in Agent.default.llm_node(
            self, chat_ctx, tools, model_settings
        ):
            yield chunk

    async def on_exit(self):
        if self.ai_mode == "local":
            await self.llm.aclose()

    async def on_enter(self):
        if self.ai_mode == "local":
            from local_models import prewarm_local

            await prewarm_local(self)
        if self.on_ready:
            await self.on_ready(self.ai_mode)


server = AgentServer(
    num_idle_processes=1,
    **(
        {"port": int(os.environ["ARIANA_AGENT_PORT"])}
        if os.getenv("ARIANA_AGENT_PORT")
        else {}
    ),
)


@server.rtc_session(
    agent_name=os.getenv("ARIANA_AGENT_NAME", "ariana"),
    on_simulation_end=check_simulation_state,
)
async def my_agent(ctx: JobContext):
    ctx.log_context_fields = {
        "room": ctx.room.name,
    }

    # Mode readiness/RPC publication requires a connected local participant.
    await ctx.connect()
    mode = initial_mode(ctx.job.metadata)
    # Each Agent owns its pipeline and turn handling; the room stays connected.
    session = AgentSession(
        userdata={},
        turn_handling=TurnHandlingOptions(
            turn_detection="realtime_llm",
        ),
    )

    install_performance(session)
    session.userdata["_ai_mode"] = mode
    configure_simulation_tools(ctx, session, Assistant)

    browser = BrowserToolset()
    session.userdata["_safari_browser"] = browser
    publisher = ActivityPublisher(ctx.room)
    session.userdata["_activity_sender"] = publisher.enqueue
    saved = "" if ctx.simulation_context() else memory_context()
    install_recovery(
        session,
        publisher,
        lambda model, chat: Assistant(
            "" if ctx.simulation_context() else memory_context(),
            model,
            chat,
            browser,
            on_ready=modes.entered,
        ),
    )
    ctx.add_shutdown_callback(publisher.close)

    modes = ModeBridge(
        ctx.room,
        session,
        lambda target, ready, chat=None: Assistant(
            "" if ctx.simulation_context() else memory_context(),
            chat_ctx=chat,
            browser=browser,
            mode=target,
            on_ready=ready,
        ),
        mode,
    )
    session.userdata["_mode_controller"] = modes
    ctx.add_shutdown_callback(modes.close)
    if mode == "local":
        from local_models import prepare_local

        await prepare_local()
    # Start the session and initialize its tools.
    await session.start(
        agent=Assistant(
            saved_context=saved, browser=browser, mode=mode, on_ready=modes.entered
        ),
        room=ctx.room,
        room_options=room_io.RoomOptions(
            # Close the session and remove the temporary console room when the user disconnects.
            delete_room_on_close=True,
            video_input=True,
            audio_input=room_io.AudioInputOptions(
                noise_cancellation=ai_coustics.audio_enhancement(
                    model=ai_coustics.EnhancerModel.QUAIL_VF_S
                ),
            ),
        ),
    )

    modes.start()
    if not ctx.simulation_context():
        controls = VoiceControls(ctx.room, session)
        controls.start()
        ctx.add_shutdown_callback(controls.close)

        async def standby_signal():
            await ctx.room.local_participant.publish_data(
                b'{"action":"standby"}', topic="ariana.conversation", reliable=True
            )

        session.userdata["_standby_sender"] = standby_signal

    # Room transport is scoped to this session and never installed in simulations.
    if not ctx.simulation_context():
        companion = CompanionBridge(
            ctx.room,
            session,
            refresh_agent=lambda chat: Assistant(
                memory_context(),
                session.current_agent.llm.model,
                chat,
                browser,
            ),
        )
        session.userdata["_companion_bridge"] = companion
        companion.start()
        ctx.add_shutdown_callback(companion.close)


if __name__ == "__main__":
    cli.run_app(server)
