"""Prepare the independent local pipeline. Fail locally; never construct Gemini here."""

import asyncio
import re

import httpx

from local_config import local_model, local_url, voice_files


async def prepare_local():
    voice_files()
    url, model = local_url(), local_model()
    try:
        async with httpx.AsyncClient(
            trust_env=False, follow_redirects=False, timeout=60
        ) as client:
            response = await client.post(url + "/api/show", json={"model": model})
            if response.status_code == 404:
                raise ValueError(
                    "Local model is missing. Pull the source model and create the ariana-local alias using ariana/local.Modelfile."
                )
            response.raise_for_status()
            data = response.json()
            if data.get("remote_host") or data.get("remote_model"):
                raise ValueError(
                    "Cloud-backed Ollama models are not allowed in Local mode."
                )
            if "tools" not in data.get("capabilities", []):
                raise ValueError(
                    "Choose a local Ollama model with native tool-call support."
                )
            context = re.search(r"num_ctx\s+(\d+)", data.get("parameters", ""))
            if not context or int(context.group(1)) < 8192:
                raise ValueError(
                    "Create a bounded local model with at least 8192 context tokens using ariana/local.Modelfile."
                )
            warm = await client.post(
                url + "/api/chat",
                json={
                    "model": model,
                    "messages": [],
                    "stream": False,
                    "think": False,
                    "keep_alive": "5m",
                    "options": {"num_ctx": 16384},
                },
            )
            warm.raise_for_status()
    except httpx.HTTPError:
        raise ValueError(
            "Ollama is unavailable. Start its local service or choose Normal Mode. Nothing was sent to Gemini."
        ) from None
    from local_speech import engines

    await asyncio.to_thread(engines)


def local_options():
    # Imports remain optional; Normal mode needs none of these dependencies/assets.
    import onnxruntime
    from livekit.agents import TurnHandlingOptions, tokenize, tts
    from livekit.plugins import openai, silero
    from openai import AsyncOpenAI

    from local_speech import LocalSTT, LocalTTS

    onnxruntime.disable_telemetry_events()
    client = AsyncOpenAI(
        api_key="ollama",
        base_url=local_url() + "/v1",
        http_client=httpx.AsyncClient(
            trust_env=False, follow_redirects=False, timeout=90
        ),
    )

    class LocalLLM(openai.LLM):
        async def aclose(self):
            await super().aclose()
            await client.close()

    return {
        "llm": LocalLLM(
            model=local_model(),
            client=client,
            temperature=0.65,
            parallel_tool_calls=False,
            reasoning_effort="none",
            extra_body={"max_tokens": 700},
            timeout=httpx.Timeout(90),
        ),
        "stt": LocalSTT(),
        "tts": tts.StreamAdapter(
            tts=LocalTTS(),
            sentence_tokenizer=tokenize.blingfire.SentenceTokenizer(
                min_sentence_len=1, stream_context_len=2, retain_format=True
            ),
        ),
        "vad": silero.VAD.load(max_buffered_speech=60),
        "turn_handling": TurnHandlingOptions(turn_detection="vad"),
    }


async def prewarm_local(agent):
    """Warm the real prompt and voice before publishing readiness. No effects/output."""
    from livekit.agents.llm.tool_context import is_function_tool

    from local_routing import visible_tools
    from local_speech import LocalTTS

    async def prompt():
        tools = visible_tools(
            [tool for tool in agent.tools if is_function_tool(tool)], ()
        )
        # Read one chunk then close: prepare the prefix, never execute generated tools.
        async with agent.llm.chat(
            chat_ctx=agent.chat_ctx.copy(), tools=tools, tool_choice="auto"
        ) as stream:
            async for chunk in stream:
                # A role-only header is not a completed prompt prefill.
                delta = getattr(chunk, "delta", None)
                if delta and (delta.content or delta.tool_calls):
                    break

    async def voice():
        async with LocalTTS().synthesize("Ready.") as stream:
            async for _ in stream:
                pass  # Warm kernels, never play a fabricated acknowledgment.

    await asyncio.wait_for(asyncio.gather(prompt(), voice()), timeout=25)
