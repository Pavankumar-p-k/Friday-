from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from friday.schemas import ToolExecutionResult
from friday.tools.base import Tool, ToolContext


class ReminderTool(Tool):
    name = "reminder"
    description = "Create, list, and complete reminders."
    input_schema = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["set", "list", "complete"]},
            "note": {"type": "string"},
            "due_at": {"type": "string"},
            "reminder_id": {"type": "integer"},
        },
        "required": ["action"],
        "additionalProperties": False,
    }

    async def execute(self, args: dict[str, Any], context: ToolContext) -> ToolExecutionResult:
        action = str(args.get("action", "")).strip().lower()

        if action == "set":
            note = str(args.get("note", "")).strip() or "Reminder"
            due_at = str(args.get("due_at", "")).strip()
            if not due_at:
                due_at = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()
            reminder_id = context.storage.add_reminder(note=note, due_at=due_at)
            return ToolExecutionResult(
                success=True,
                message=f"Reminder created: {note}",
                data={"id": reminder_id, "note": note, "due_at": due_at},
            )

        if action == "list":
            reminders = context.storage.list_reminders(include_done=False)
            return ToolExecutionResult(
                success=True,
                message=f"Found {len(reminders)} active reminders.",
                data={"reminders": reminders},
            )

        if action == "complete":
            reminder_id = args.get("reminder_id")
            if reminder_id is None:
                return ToolExecutionResult(success=False, message="Missing reminder_id.")
            ok = context.storage.complete_reminder(int(reminder_id))
            if ok:
                return ToolExecutionResult(
                    success=True,
                    message=f"Reminder {reminder_id} completed.",
                    data={"reminder_id": int(reminder_id)},
                )
            return ToolExecutionResult(
                success=False,
                message=f"Reminder {reminder_id} not found.",
            )

        return ToolExecutionResult(success=False, message=f"Unsupported reminder action '{action}'.")
