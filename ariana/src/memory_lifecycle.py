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
    columns = {row[1] for row in db.execute("PRAGMA table_info(memory_details)")}
    if "importance" not in columns:
        db.execute(
            "ALTER TABLE memory_details ADD COLUMN importance INTEGER NOT NULL DEFAULT 3"
        )
    db.execute(
        "CREATE TABLE IF NOT EXISTS project_history (id INTEGER PRIMARY KEY, topic TEXT NOT NULL REFERENCES facts(topic) ON DELETE CASCADE, summary TEXT NOT NULL, recorded_at REAL NOT NULL)"
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
            "SELECT topic,kind,expires_at,follow_up_at,followed_up,revision,importance FROM memory_details"
        )
    }
    return [
        dict(
            topic=topic,
            fact=fact,
            previous_summaries=history(db, topic),
            **dict(
                zip(
                    (
                        "kind",
                        "expires_at",
                        "follow_up_at",
                        "followed_up",
                        "revision",
                        "importance",
                    ),
                    metadata.get(topic, ("fact", None, None, 0, "legacy", 3)),
                    strict=True,
                )
            ),
        )
        for topic, fact in rows
    ]


def progress(db, topic, fact):
    """Keep two prior project summaries, never raw transcript or false corrections."""
    old = db.execute(
        "SELECT f.fact,d.kind FROM facts f JOIN memory_details d USING(topic) WHERE topic=?",
        (topic,),
    ).fetchone()
    if not old or old[1] != "project":
        raise ValueError("Progress needs an existing project; recall its topic first.")
    if old[0] == fact:
        return (
            False  # A repeated update must not extend retention or cancel a reminder.
        )
    db.execute(
        "INSERT INTO project_history(topic,summary,recorded_at) VALUES (?,?,?)",
        (topic, old[0], time.time()),
    )
    db.execute(
        "DELETE FROM project_history WHERE topic=? AND id NOT IN (SELECT id FROM project_history WHERE topic=? ORDER BY id DESC LIMIT 2)",
        (topic, topic),
    )
    return True


def history(db, topic):
    return [
        {"summary": summary, "recorded_at": recorded}
        for summary, recorded in db.execute(
            "SELECT summary,recorded_at FROM project_history WHERE topic=? ORDER BY id",
            (topic,),
        )
    ]


def validate_importance_threshold(value):
    if type(value) is not int or not 1 <= value <= 5:
        raise ValueError("Minimum importance must be a whole number from 1 to 5.")
