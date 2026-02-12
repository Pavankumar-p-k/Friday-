from __future__ import annotations

from typing import Any

from friday.config import Settings
from friday.llm import LocalLLMClient
from friday.schemas import ToolExecutionResult
from friday.storage import Storage
from friday.tools.base import Tool, ToolContext
from friday.tools.code_agent import CodeAgentTool
from friday.tools.media_control import MediaControlTool
from friday.tools.open_app import OpenAppTool
from friday.tools.reminder import ReminderTool
from friday.tools.safe_shell import SafeShellTool


class ToolRegistry:
    def __init__(self, context: ToolContext) -> None:
        self._context = context
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def has_tool(self, name: str) -> bool:
        return name in self._tools

    def list_tools(self) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        for tool in self._tools.values():
            entries.append(
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.input_schema,
                }
            )
        return entries

    async def execute(self, name: str, args: dict[str, Any]) -> ToolExecutionResult:
        tool = self._tools.get(name)
        if tool is None:
            return ToolExecutionResult(success=False, message=f"Unknown tool: {name}")
        return await tool.execute(args, self._context)


def build_default_registry(
    settings: Settings,
    storage: Storage,
    llm: LocalLLMClient,
) -> ToolRegistry:
    context = ToolContext(settings=settings, storage=storage, llm=llm)
    registry = ToolRegistry(context)
    registry.register(OpenAppTool())
    registry.register(MediaControlTool())
    registry.register(ReminderTool())
    registry.register(CodeAgentTool())
    registry.register(SafeShellTool())
    return registry
