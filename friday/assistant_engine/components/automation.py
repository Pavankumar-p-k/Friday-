from __future__ import annotations

import asyncio

from friday.assistant_engine.interfaces import AutomationExecutor, AutomationHandler
from friday.assistant_engine.models import AutomationResult


class InProcessAutomationExecutor(AutomationExecutor):
    def __init__(self) -> None:
        self._handlers: dict[str, AutomationHandler] = {}

    def register(self, action_name: str, handler: AutomationHandler) -> None:
        self._handlers[action_name.strip().lower()] = handler

    async def execute(self, action_name: str, command: str) -> AutomationResult:
        key = action_name.strip().lower()
        handler = self._handlers.get(key)
        if handler is None:
            return AutomationResult(
                success=False,
                action=key,
                message=f"No automation handler registered for '{key}'.",
                data={"command": command},
            )
        return await asyncio.to_thread(handler, command)


def default_automation_handler(command: str) -> AutomationResult:
    return AutomationResult(
        success=True,
        action="default",
        message="Automation scaffold executed command.",
        data={"command": command},
    )
