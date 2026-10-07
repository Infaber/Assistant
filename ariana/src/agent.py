import logging
import os
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
from browser_tools import BrowserToolset
from companion import CompanionBridge
from instructions import ARIANA_INSTRUCTIONS
from mac_tools import mac_control
from memory_tools import memory_context, memory_manage
from model_config import realtime_model
from notes_tools import notes_edit, notes_list, notes_read
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
        self, saved_context: str = "", model_name: str = "", chat_ctx=None, browser=None
    ) -> None:
        super().__init__(
            chat_ctx=chat_ctx,
            llm=realtime_model(_google_api_key(), model_name),
            tools=[
                search_web,
                home_assistant_request,
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
                assistant_status,
                task_status,
                browser or BrowserToolset(),
            ],
            instructions=ARIANA_INSTRUCTIONS + saved_context,
        )


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

    # Gemini handles speech input, speech output, and turn detection.
    session = AgentSession(
        userdata={},
        turn_handling=TurnHandlingOptions(
            turn_detection="realtime_llm",
        ),
    )

    configure_simulation_tools(ctx, session, Assistant)

    browser = BrowserToolset()
    session.userdata["_safari_browser"] = browser
    publisher = ActivityPublisher(ctx.room)
    session.userdata["_activity_sender"] = publisher.enqueue
    saved = "" if ctx.simulation_context() else memory_context()
    install_recovery(
        session, publisher, lambda model, chat: Assistant(saved, model, chat, browser)
    )
    ctx.add_shutdown_callback(publisher.close)

    # Start the session and initialize its tools.
    await session.start(
        agent=Assistant(saved_context=saved, browser=browser),
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

    # Room transport is scoped to this session and never installed in simulations.
    if not ctx.simulation_context():
        companion = CompanionBridge(
            ctx.room,
            session,
            refresh_agent=lambda chat: Assistant(
                saved,
                session.current_agent.llm.model,
                chat,
                browser,
            ),
        )
        companion.start()
        ctx.add_shutdown_callback(companion.close)

    # Join the room and connect to the user
    await ctx.connect()


if __name__ == "__main__":
    cli.run_app(server)
