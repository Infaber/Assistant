"""Session-local action receipts. No execution, replay, credentials or persisted data."""

import hashlib
import json
import time
from dataclasses import dataclass

from livekit.agents import RunContext, function_tool


@dataclass
class Receipt:
    id: str
    label: str
    status: str
    fingerprint: str
    write: bool
    timestamp: float


class TaskLedger:
    def __init__(self):
        self.receipts: list[Receipt] = []

    def previous_write(self, fingerprint):
        return next(
            (
                row
                for row in reversed(self.receipts)
                if row.write
                and row.fingerprint == fingerprint
                and row.status in {"running", "returned", "verified", "uncertain"}
            ),
            None,
        )

    def begin(self, receipt_id, label, fingerprint, write):
        if write and sum(row.write for row in self.receipts) >= 100:
            # Never evict unresolved or completed write receipts to enable a replay.
            raise ValueError(
                "Action history is full. Start a fresh session after checking unfinished actions."
            )
        receipt = Receipt(receipt_id, label, "running", fingerprint, write, time.time())
        reads = [row for row in self.receipts if not row.write]
        if len(reads) >= 40:
            self.receipts.remove(reads[0])
        self.receipts.append(receipt)
        return receipt

    def summary(self):
        return [
            {"id": r.id, "step": r.label, "status": r.status} for r in self.receipts
        ]


def ledger_for(context):
    try:
        state = context.session.userdata
        return state.setdefault("_task_ledger", TaskLedger())
    except (AttributeError, ValueError, TypeError):
        return None


def action_fingerprint(name, arguments):
    clean = {
        key: value
        for key, value in arguments.items()
        if key not in {"context", "self", "confirmed", "snapshot_id"}
    }
    return hashlib.sha256(
        json.dumps([name, clean], sort_keys=True, default=str).encode()
    ).hexdigest()


def is_write(name, arguments):
    if name in {
        "notes_create",
        "notes_edit",
        "calendar_create_event",
        "reminders_create",
        "mail_send",
    }:
        return arguments.get("confirmed", False)
    if name == "mac_control":
        return arguments.get("action") in {
            "click",
            "type",
            "shortcut",
            "scroll",
            "double_click",
            "context_click",
        }
    return False


@function_tool
async def task_status(context: RunContext) -> dict:
    """Read this session's action receipts for multi-step progress or recovery.
    Only verified receipts prove outcomes. Returned means dispatched/result returned,
    not verified. Keep completed steps; inspect uncertain outcomes before considering
    another action. This cannot confirm, reset, execute, or retry any action.
    """
    ledger = ledger_for(context)
    return {"steps": ledger.summary() if ledger else []}
