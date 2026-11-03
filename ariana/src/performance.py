"""Bounded, numerical session diagnostics. No transcripts, arguments or model payloads.

SDK latency is server-side; it does not measure sound reaching the user's ears.
See https://docs.livekit.io/testing/observability/data/ for metric definitions.
"""

import logging
import math
import statistics
from collections import deque
from contextlib import contextmanager
from time import monotonic

logger = logging.getLogger("ariana.performance")
LATENCIES = frozenset(
    {
        "transcription_delay",
        "end_of_turn_delay",
        "on_user_turn_completed_delay",
        "llm_node_ttft",
        "llm_node_ttfs",
        "tts_node_ttfb",
        "playback_latency",
        "e2e_latency",
    }
)


class Performance:
    def __init__(self, clock=monotonic):
        self.clock = clock
        self.samples = deque(maxlen=100)

    def record(self, stage, seconds):
        if not isinstance(seconds, (int, float)) or isinstance(seconds, bool):
            return
        if not math.isfinite(seconds) or seconds < 0:
            return
        row = {"stage": stage, "milliseconds": round(seconds * 1000, 2)}
        self.samples.append(row)
        logger.info("latency stage=%s milliseconds=%s", stage, row["milliseconds"])

    @contextmanager
    def measure(self, stage):
        start = self.clock()
        try:
            yield
        finally:
            self.record(stage, self.clock() - start)

    def summary(self):
        stages = {}
        for row in self.samples:
            stages.setdefault(row["stage"], []).append(row["milliseconds"])
        return {
            name: {
                "samples": len(values),
                "mean_ms": round(sum(values) / len(values), 2),
                "max_ms": max(values),
                "median_ms": round(statistics.median(values), 2),
                "p95_ms": sorted(values)[math.ceil(0.95 * len(values)) - 1],
            }
            for name, values in stages.items()
        }


def for_session(session):
    try:
        return session.userdata.setdefault("_performance", Performance())
    except (AttributeError, TypeError, ValueError):
        return Performance()


def install_performance(session):
    performance = for_session(session)

    @session.on("conversation_item_added")
    def item_added(event):
        # Explicit allowlist excludes text, timestamps, provider IDs and metadata.
        for name, value in getattr(event.item, "metrics", {}).items():
            if name in LATENCIES:
                performance.record(name, value)

    timing = {"user_end": None, "overlap": None, "speaking": False}

    @session.on("user_state_changed")
    def user_state(event):
        now = performance.clock()
        if event.new_state == "speaking":
            timing["user_end"] = None
            if timing["speaking"]:
                timing["overlap"] = now
        elif event.old_state == "speaking":
            timing["user_end"] = now

    @session.on("agent_state_changed")
    def agent_state(event):
        now = performance.clock()
        speaking = event.new_state == "speaking"
        if speaking and not timing["speaking"] and timing["user_end"] is not None:
            performance.record(
                "sdk_user_end_to_speaking_state", now - timing["user_end"]
            )
            timing["user_end"] = None
        if not speaking and timing["speaking"] and timing["overlap"] is not None:
            performance.record(
                "sdk_overlap_to_speaking_state_stop", now - timing["overlap"]
            )
            timing["overlap"] = None
        timing["speaking"] = speaking

    pending = {}

    @session.on("tool_execution_updated")
    def tool_updated(event):
        update = event.update
        if update.type == "tool_call_started":
            call_id = update.function_call.call_id
            if call_id not in pending:
                if len(pending) >= 64:
                    pending.pop(next(iter(pending)))
                pending[call_id] = performance.clock()
        elif update.type == "tool_call_ended":
            started = pending.pop(update.call_id, None)
            if started is not None:
                # Includes direct integrations without @observed. Ignore names,
                # arguments, result messages and whether a write succeeded.
                performance.record("tool_execution", performance.clock() - started)

    @session.on("close")
    def closed(event):
        pending.clear()
        timing.update(user_end=None, overlap=None, speaking=False)

    return performance
