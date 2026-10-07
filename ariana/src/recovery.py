"""Bounded model recovery with clear errors, never replaying user tool actions."""

import os
from uuid import uuid4

from model_config import configured_model


def describe_failure(error):
    # Classify provider errors, not user intent. Never publish raw provider payloads.
    details = str(getattr(error, "error", error)).casefold()
    if any(
        word in details for word in ("quota", "resource_exhausted", "429", "rate limit")
    ):
        return (
            "model_quota",
            "The voice provider has reached a usage limit. Check its quota or billing, then reconnect.",
        )
    if any(
        word in details
        for word in ("api key", "unauthorized", "401", "permission_denied")
    ):
        return (
            "model_auth",
            "The voice provider rejected its credentials. Check the agent's API key, then reconnect.",
        )
    return (
        "model_unavailable",
        "Ariana's voice connection failed. Reconnect to start a fresh session; uncertain actions will not be replayed.",
    )


def install_recovery(session, publisher, make_agent):
    attempted_backup = False

    @session.on("error")
    def on_error(event):
        nonlocal attempted_backup
        code, detail = describe_failure(event.error)
        if getattr(event.error, "recoverable", False):
            publisher.publish(
                {
                    "id": uuid4().hex,
                    "kind": "system",
                    "label": "Voice connection",
                    "status": "recovering",
                    "detail": "The voice provider is reconnecting. No actions are being replayed.",
                }
            )
            return
        backup = os.getenv("ARIANA_FALLBACK_GOOGLE_MODEL", "").strip()
        primary = configured_model()
        if (
            backup
            and backup != primary
            and not attempted_backup
            and code != "model_auth"
        ):
            attempted_backup = True
            event.error.recoverable = True
            # Carry completed tool outputs across handoff, but never resubmit a turn.
            try:
                agent = make_agent(backup, session.current_agent.chat_ctx.copy())
                session.update_agent(agent)
                publisher.publish(
                    {
                        "id": uuid4().hex,
                        "kind": "system",
                        "label": "Backup voice model",
                        "status": "recovering",
                        "detail": "Switching to the configured backup. Repeat your question when ready; previous actions will not be replayed.",
                    }
                )
                return
            except Exception:
                event.error.recoverable = False
        publisher.publish(
            {
                "id": uuid4().hex,
                "kind": "system",
                "label": "Voice connection",
                "status": "failed",
                "code": code,
                "detail": detail,
            }
        )
