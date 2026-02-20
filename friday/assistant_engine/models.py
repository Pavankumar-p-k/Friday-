from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any
import time


class AssistantMode(str, Enum):
    CHAT = "chat"
    ACTION = "action"
    CODE = "code"


class IntentType(str, Enum):
    CHAT = "chat"
    AUTOMATION = "automation"
    CODE = "code"
    UNKNOWN = "unknown"


class EventType(str, Enum):
    ENGINE_STARTED = "engine.started"
    ENGINE_STOPPED = "engine.stopped"
    AUDIO_RECEIVED = "audio.received"
    TRANSCRIPT_PARTIAL = "transcript.partial"
    TRANSCRIPT_FINAL = "transcript.final"
    WAKE_WORD_DETECTED = "wake_word.detected"
    WAKE_WORD_MISSED = "wake_word.missed"
    INTENT_CLASSIFIED = "intent.classified"
    LLM_RESPONSE = "llm.response"
    TTS_READY = "tts.ready"
    AUTOMATION_EXECUTED = "automation.executed"
    ERROR = "error"


def now_ts() -> float:
    return time.time()


@dataclass(slots=True, frozen=True)
class AudioFrame:
    session_id: str
    payload: bytes
    is_final: bool = False
    timestamp: float = field(default_factory=now_ts)


@dataclass(slots=True, frozen=True)
class TranscriptUpdate:
    session_id: str
    text: str
    is_final: bool
    confidence: float = 0.0
    backend: str = "running-text"
    timestamp: float = field(default_factory=now_ts)


@dataclass(slots=True, frozen=True)
class IntentResult:
    intent: IntentType
    confidence: float
    mode: AssistantMode
    extracted_command: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class LLMRequest:
    session_id: str
    prompt: str
    intent: IntentResult


@dataclass(slots=True, frozen=True)
class LLMResponse:
    text: str
    backend: str
    latency_ms: int


@dataclass(slots=True, frozen=True)
class TTSResult:
    audio_path: str
    backend: str


@dataclass(slots=True, frozen=True)
class AutomationResult:
    success: bool
    action: str
    message: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class EngineEvent:
    event_type: EventType
    session_id: str
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=now_ts)
