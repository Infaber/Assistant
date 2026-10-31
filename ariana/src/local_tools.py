"""Report the actual active engine without granting mode-switch permissions."""

import httpx
from livekit.agents import RunContext
from livekit.agents.llm import function_tool

from local_config import local_model, local_url


@function_tool
async def ai_engine_status(context: RunContext, check_local: bool = False) -> dict:
    """Read the actual AI mode/model. check_local also checks Ollama from Normal mode. Checks local Ollama only; never switches modes."""
    mode = context.session.userdata.get("_ai_mode", "normal")
    active = context.session.current_agent.llm.model
    if mode != "local" and not check_local:
        return {"mode": mode, "model": active}
    try:
        async with httpx.AsyncClient(
            trust_env=False, timeout=3, follow_redirects=False
        ) as client:
            result = await client.get(local_url() + "/api/ps")
            result.raise_for_status()
        loaded = any(
            row.get("name") == local_model() for row in result.json().get("models", [])
        )
        return {
            "mode": mode,
            "model": active,
            "local_model": local_model(),
            "ollama_available": True,
            "model_loaded": loaded,
            "cloud_inference": mode != "local",
        }
    except httpx.HTTPError:
        return {
            "mode": mode,
            "model": active,
            "error": "Ollama unavailable; the active engine was not changed.",
        }
