"""Single-use camera consent, scoped to a later genuine user turn."""

import json
import time


def approval(context, operation, payload, confirmed):
    state = context.session.userdata
    users = [
        item
        for item in context.session.history.items
        if getattr(item, "role", None) == "user"
        and not str(item.id).startswith(("camera-event-", "camera-image-"))
    ]
    if not users:
        return {"error": "Ask the user directly; camera consent is missing."}
    fingerprint = json.dumps([operation, payload], sort_keys=True)
    pending = state.get("_camera_consent")
    now = time.monotonic()
    # Validate recipient disclosure, not the user's wording or affirmative intent.
    # Tool/page text cannot satisfy this: only genuine spoken conversation messages.
    disclosed = operation != "snapshot"
    if pending and operation == "snapshot":
        messages = context.session.history.items[pending.get("history_size", 0) :]
        for item in messages:
            if getattr(item, "role", None) not in {"assistant", "user"} or str(
                item.id
            ).startswith(("camera-event-", "camera-image-")):
                continue
            text = str(getattr(item, "text_content", "")).casefold()
            if "gemini" in text and any(
                word in text for word in ("image", "snapshot", "picture")
            ):
                disclosed = True
    if (
        confirmed
        and disclosed
        and pending
        and pending["fingerprint"] == fingerprint
        and len(users) == pending["count"] + 1
        and users[-1].id != pending["turn"]
        and now - pending["time"] < 300
    ):
        state.pop("_camera_consent", None)
        return None
    state["_camera_consent"] = {
        "fingerprint": fingerprint,
        "count": len(users),
        "turn": users[-1].id,
        "time": now,
        "history_size": len(context.session.history.items),
    }
    disclosure = (
        "send one camera image to Google Gemini for this question"
        if operation == "snapshot"
        else "enable neutral camera announcements for this connected session"
    )
    return {
        "requires_confirmation": True,
        "preview": f"Ask permission to {disclosure}. Wait for a NEW user reply; natural affirmative approval is enough. Then call again with identical arguments and confirmed=true. No camera image has been retrieved.",
        "details": payload,
    }
