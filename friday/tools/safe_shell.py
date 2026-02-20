from __future__ import annotations

import re
import shlex
import subprocess
from typing import Any

from friday.schemas import ToolExecutionResult
from friday.tools.base import Tool, ToolContext


_POWERSHELL_CMDLET_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]*-[A-Za-z][A-Za-z0-9]*$")
_BLOCKED_CONTROL_OPERATORS: tuple[str, ...] = (
    "&&",
    "||",
    "|",
    ";",
    "<",
    ">",
    "$(",
    "`",
    "&",
)


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
        timeout_sec = max(1, min(120, int(args.get("timeout_sec", 12))))

        if not command:
            return ToolExecutionResult(success=False, message="Missing command.")

        if self._contains_line_break(command):
            return ToolExecutionResult(
                success=False,
                message="Command blocked: contains forbidden line break.",
                data={"command": command},
            )

        if self._contains_control_operators(command):
            return ToolExecutionResult(
                success=False,
                message="Command blocked: contains forbidden shell control operator.",
                data={"command": command},
            )

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
            run_args = self._build_run_args(command)
            result = subprocess.run(
                run_args,
                shell=False,
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
                    "executed_as": run_args,
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

    def _build_run_args(self, command: str) -> list[str]:
        try:
            tokens = shlex.split(command, posix=False)
        except ValueError:
            tokens = []
        first = tokens[0] if tokens else command.split(" ", 1)[0]
        if _POWERSHELL_CMDLET_RE.match(first):
            return ["powershell", "-NoProfile", "-Command", command]
        return ["cmd", "/c", command]

    def _is_allowed(self, command: str, allowed_prefixes: tuple[str, ...]) -> bool:
        lowered = command.strip().lower()
        for prefix in allowed_prefixes:
            normalized = prefix.strip().lower()
            if not normalized:
                continue
            if lowered == normalized:
                return True
            if lowered.startswith(normalized) and len(lowered) > len(normalized):
                if lowered[len(normalized)].isspace():
                    return True
        return False

    def _contains_line_break(self, command: str) -> bool:
        if "\n" in command or "\r" in command:
            return True
        return False

    def _contains_control_operators(self, command: str) -> bool:
        lowered = command.lower()
        for operator in _BLOCKED_CONTROL_OPERATORS:
            if operator in lowered:
                return True
        return False

    def _contains_blocked_term(self, command: str, blocked_terms: tuple[str, ...]) -> bool:
        lowered = f" {command.lower()} "
        for term in blocked_terms:
            if term.lower() in lowered:
                return True
        return False
