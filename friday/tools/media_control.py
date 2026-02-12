from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from friday.schemas import ToolExecutionResult
from friday.tools.base import Tool, ToolContext


class MediaControlTool(Tool):
    name = "media_control"
    description = "Control local media playback with lightweight commands."
    input_schema = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["play", "pause", "resume", "stop", "next", "previous"]},
            "target": {"type": "string"},
        },
        "required": ["action"],
        "additionalProperties": False,
    }

    async def execute(self, args: dict[str, Any], context: ToolContext) -> ToolExecutionResult:
        action = str(args.get("action", "")).strip().lower()
        target = str(args.get("target", "")).strip()

        if action not in {"play", "pause", "resume", "stop", "next", "previous"}:
            return ToolExecutionResult(success=False, message=f"Unsupported action '{action}'.")

        if action == "play" and target:
            path = Path(target)
            if path.exists():
                try:
                    os.startfile(str(path))  # type: ignore[attr-defined]
                    return ToolExecutionResult(
                        success=True,
                        message=f"Playing file: {path}",
                        data={"action": action, "target": str(path)},
                    )
                except Exception as exc:
                    return ToolExecutionResult(success=False, message=f"Failed to play media: {exc}")

        return ToolExecutionResult(
            success=True,
            message=f"Media action accepted: {action}.",
            data={"action": action, "target": target or "default"},
        )

