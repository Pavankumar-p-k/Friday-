from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable, Protocol

from friday.assistant_engine.models import (
    AudioFrame,
    AutomationResult,
    IntentResult,
    LLMRequest,
    LLMResponse,
    TranscriptUpdate,
    TTSResult,
)


class WakeWordDetector(Protocol):
    def detect(self, text: str) -> tuple[bool, str]:
        """Return (detected, command_without_wake_word)."""


class RunningSTT(ABC):
    @abstractmethod
    async def transcribe(self, frame: AudioFrame) -> TranscriptUpdate:
        raise NotImplementedError


class IntentClassifier(ABC):
    @abstractmethod
    async def classify(self, text: str) -> IntentResult:
        raise NotImplementedError


class LLMBridge(ABC):
    @abstractmethod
    async def generate(self, request: LLMRequest) -> LLMResponse:
        raise NotImplementedError


class TTSAdapter(ABC):
    @abstractmethod
    async def speak(self, session_id: str, text: str) -> TTSResult:
        raise NotImplementedError


AutomationHandler = Callable[[str], AutomationResult]


class AutomationExecutor(ABC):
    @abstractmethod
    async def execute(self, action_name: str, command: str) -> AutomationResult:
        raise NotImplementedError
