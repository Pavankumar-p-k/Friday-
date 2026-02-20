from __future__ import annotations

import asyncio
from pathlib import Path

from friday.assistant_engine.components.automation import InProcessAutomationExecutor
from friday.assistant_engine.components.intent import RuleBasedIntentClassifier
from friday.assistant_engine.components.stt import RunningTextSTT
from friday.assistant_engine.components.wakeword import KeywordWakeWordDetector
from friday.assistant_engine.config import EngineConfig
from friday.assistant_engine.interfaces import LLMBridge, TTSAdapter
from friday.assistant_engine.models import (
    AutomationResult,
    EventType,
    LLMRequest,
    LLMResponse,
    TTSResult,
)
from friday.assistant_engine.runtime import AssistantEngine


class FakeLLMBridge(LLMBridge):
    async def generate(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(
            text=f"ack:{request.prompt}",
            backend="fake-local",
            latency_ms=1,
        )


class FakeTTSAdapter(TTSAdapter):
    def __init__(self, output_dir: Path) -> None:
        self._output_dir = output_dir
        self._output_dir.mkdir(parents=True, exist_ok=True)

    async def speak(self, session_id: str, text: str) -> TTSResult:
        target = self._output_dir / f"{session_id}.txt"
        target.write_text(text, encoding="utf-8")
        return TTSResult(audio_path=str(target), backend="fake-tts")


async def _drain_events_until(
    engine: AssistantEngine,
    stop_event: EventType,
    timeout_sec: float = 2.0,
) -> list[EventType]:
    seen: list[EventType] = []
    stream = engine.events()
    try:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout_sec
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise TimeoutError(f"Timed out waiting for {stop_event.value}")
            event = await asyncio.wait_for(stream.__anext__(), timeout=remaining)
            seen.append(event.event_type)
            if event.event_type == stop_event:
                return seen
    finally:
        await stream.aclose()


def test_engine_processes_wake_word_and_automation(tmp_path: Path) -> None:
    config = EngineConfig(
        wake_words=("friday",),
        require_wake_word=True,
        stt_emit_partials=False,
        tts_output_dir=tmp_path / "tts",
    )
    automation = InProcessAutomationExecutor()
    automation.register(
        "open_app",
        lambda command: AutomationResult(
            success=True,
            action="open_app",
            message="opened",
            data={"command": command},
        ),
    )

    engine = AssistantEngine(
        config=config,
        wake_word_detector=KeywordWakeWordDetector(config.wake_words),
        stt=RunningTextSTT(emit_partials=False),
        intent_classifier=RuleBasedIntentClassifier(),
        llm_bridge=FakeLLMBridge(),
        tts=FakeTTSAdapter(config.tts_output_dir),
        automation=automation,
    )

    async def _scenario() -> list[EventType]:
        await engine.start()
        await engine.submit_text("s1", "hey friday open notepad", is_final=True)
        seen = await _drain_events_until(engine, EventType.TTS_READY)
        await engine.stop()
        return seen

    seen_types = asyncio.run(_scenario())
    assert EventType.WAKE_WORD_DETECTED in seen_types
    assert EventType.INTENT_CLASSIFIED in seen_types
    assert EventType.AUTOMATION_EXECUTED in seen_types
    assert EventType.TTS_READY in seen_types


def test_engine_skips_without_wake_word(tmp_path: Path) -> None:
    config = EngineConfig(
        wake_words=("friday",),
        require_wake_word=True,
        stt_emit_partials=False,
        tts_output_dir=tmp_path / "tts2",
    )
    engine = AssistantEngine(
        config=config,
        wake_word_detector=KeywordWakeWordDetector(config.wake_words),
        stt=RunningTextSTT(emit_partials=False),
        intent_classifier=RuleBasedIntentClassifier(),
        llm_bridge=FakeLLMBridge(),
        tts=FakeTTSAdapter(config.tts_output_dir),
        automation=InProcessAutomationExecutor(),
    )

    async def _scenario() -> list[EventType]:
        await engine.start()
        await engine.submit_text("s2", "open notepad", is_final=True)
        seen = await _drain_events_until(engine, EventType.WAKE_WORD_MISSED)
        await engine.stop()
        return seen

    seen_types = asyncio.run(_scenario())
    assert EventType.WAKE_WORD_MISSED in seen_types
    assert EventType.TTS_READY not in seen_types
