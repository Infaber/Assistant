"""Local memory types, expiry and single-use conversational follow-ups."""

import time
from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

KINDS = {"fact", "preference", "project", "event"}


def date_value(value):
    if not value:
        return None
    try:
        date = datetime.fromisoformat(value)
        if date.tzinfo is None:
            date = date.replace(tzinfo=ZoneInfo("Europe/Oslo"))
        return date.timestamp()
    except (ValueError, TypeError, OverflowError):
        raise ValueError(
            "Use an ISO date/time for a follow-up, preferably with a timezone offset."
        ) from None


def validate(request, now=None):
    now = time.time() if now is None else now
    kind = request.get("kind", "")
    retention = request.get("retention_days", 0)
    if (
        kind not in KINDS | {""}
        or type(retention) is not int
        or not 0 <= retention <= 365
    ):
        raise ValueError(
            "Choose fact/preference/project/event and retention_days from 0 to 365."
        )
    follow = date_value(request.get("follow_up_at", ""))
    if follow is not None and (
        kind not in {"project", "event"} or not now < follow <= now + 180 * 86400
    ):
        raise ValueError(
            "Follow-ups need an event/project and a future date within 180 days."
        )
    return kind, retention, follow


def schema(db):
    db.execute(
        "CREATE TABLE IF NOT EXISTS memory_details (topic TEXT PRIMARY KEY REFERENCES facts(topic) ON DELETE CASCADE, kind TEXT NOT NULL, expires_at REAL, follow_up_at REAL, followed_up INTEGER NOT NULL DEFAULT 0, revision TEXT NOT NULL)"
    )
    db.execute(
        "DELETE FROM facts WHERE topic IN (SELECT topic FROM memory_details WHERE expires_at IS NOT NULL AND expires_at<=?)",
        (time.time(),),
    )


def save(db, topic, kind, retention, follow):
    old = db.execute(
        "SELECT kind FROM memory_details WHERE topic=?", (topic,)
    ).fetchone()
    kind = kind or (old[0] if old else "fact")
    days = retention or {"event": 30, "project": 180}.get(kind, 0)
    expires = time.time() + days * 86400 if days else None
    if follow is not None and expires is not None and follow >= expires:
        raise ValueError("The follow-up must occur before this memory expires.")
    db.execute(
        "INSERT INTO memory_details(topic,kind,expires_at,follow_up_at,followed_up,revision) VALUES (?,?,?,?,0,?) ON CONFLICT(topic) DO UPDATE SET kind=excluded.kind,expires_at=excluded.expires_at,follow_up_at=excluded.follow_up_at,followed_up=0,revision=excluded.revision",
        (topic, kind, expires, follow, uuid4().hex),
    )


def details(db, rows):
    metadata = {
        row[0]: row[1:]
        for row in db.execute(
            "SELECT topic,kind,expires_at,follow_up_at,followed_up,revision FROM memory_details"
        )
    }
    return [
        dict(
            topic=topic,
            fact=fact,
            **dict(
                zip(
                    ("kind", "expires_at", "follow_up_at", "followed_up", "revision"),
                    metadata.get(topic, ("fact", None, None, 0, "legacy")),
                    strict=True,
                )
            ),
        )
        for topic, fact in rows
    ]
