from __future__ import annotations

import subprocess
from typing import Any

from friday.schemas import ToolExecutionResult
from friday.tools.base import Tool, ToolContext


class SafeShellTool(Tool):
    name = "safe_shell"
    description = "Run allowlisted shell commands with strict prefix checks."
    input_schema = {
        "type": "object",
        "properties": {
            "command": {"type": "string"},
            "timeout_sec": {"type": "integer"},
        },
        "required": ["command"],
        "additionalProperties": False,
    }

    async def execute(self, args: dict[str, Any], context: ToolContext) -> ToolExecutionResult:
        command = str(args.get("command", "")).strip()
        timeout_sec = int(args.get("timeout_sec", 12))

        if not command:
            return ToolExecutionResult(success=False, message="Missing command.")

        if self._contains_blocked_term(command, context.settings.blocked_shell_terms):
            return ToolExecutionResult(
                success=False,
                message="Command blocked: contains blocked term.",
                data={"command": command},
            )

        if not self._is_allowed(command, context.settings.allowed_shell_prefixes):
            return ToolExecutionResult(
                success=False,
                message="Command blocked: not in shell allowlist.",
                data={"command": command},
            )

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
            )
            success = result.returncode == 0
            return ToolExecutionResult(
                success=success,
                message="Command executed." if success else "Command failed.",
                data={
                    "command": command,
                    "returncode": result.returncode,
                    "stdout": result.stdout[-4000:],
                    "stderr": result.stderr[-4000:],
                },
            )
        except Exception as exc:
            return ToolExecutionResult(
                success=False,
                message=f"Shell execution error: {exc}",
                data={"command": command},
            )

    def _is_allowed(self, command: str, allowed_prefixes: tuple[str, ...]) -> bool:
        lowered = command.strip().lower()
        for prefix in allowed_prefixes:
            if lowered.startswith(prefix.lower()):
                return True
        return False

    def _contains_blocked_term(self, command: str, blocked_terms: tuple[str, ...]) -> bool:
        lowered = f" {command.lower()} "
        for term in blocked_terms:
            if term.lower() in lowered:
                return True
        return False
