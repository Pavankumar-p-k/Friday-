from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from friday.config import Settings
from friday.llm import LocalLLMClient
from friday.schemas import ToolExecutionResult
from friday.storage import Storage


@dataclass(frozen=True)
class ToolContext:
    settings: Settings
    storage: Storage
    llm: LocalLLMClient


class Tool(ABC):
    name: str
    description: str
    input_schema: dict[str, Any]

    @abstractmethod
    async def execute(self, args: dict[str, Any], context: ToolContext) -> ToolExecutionResult:
        raise NotImplementedError

