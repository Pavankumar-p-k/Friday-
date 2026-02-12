from __future__ import annotations

import subprocess
from typing import Any

from friday.schemas import ToolExecutionResult
from friday.tools.base import Tool, ToolContext


class OpenAppTool(Tool):
    name = "open_app"
    description = "Open allowlisted desktop applications."
    input_schema = {
        "type": "object",
        "properties": {"app_name": {"type": "string"}},
        "required": ["app_name"],
        "additionalProperties": False,
    }

    async def execute(self, args: dict[str, Any], context: ToolContext) -> ToolExecutionResult:
        app_name = str(args.get("app_name", "")).strip().lower()
        if not app_name:
            return ToolExecutionResult(success=False, message="Missing app_name.")

        if app_name not in context.settings.allowed_apps:
            return ToolExecutionResult(
                success=False,
                message=f"App '{app_name}' is not in allowlist.",
            )

        app_command = context.settings.allowed_apps[app_name]
        try:
            subprocess.Popen(app_command, shell=True)
            return ToolExecutionResult(
                success=True,
                message=f"Opened {app_name}.",
                data={"app_name": app_name, "command": app_command},
            )
        except Exception as exc:
            return ToolExecutionResult(success=False, message=f"Failed to open app: {exc}")

