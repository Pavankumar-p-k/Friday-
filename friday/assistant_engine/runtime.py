from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import AsyncIterator

from friday.assistant_engine.components import (
    CloudLLMBridge,
    FileTTSAdapter,
    HybridLLMBridge,
    InProcessAutomationExecutor,
    KeywordWakeWordDetector,
    LocalLLMBridge,
    RuleBasedIntentClassifier,
    RunningTextSTT,
    default_automation_handler,
)
from friday.assistant_engine.config import EngineConfig
from friday.assistant_engine.interfaces import (
    AutomationExecutor,
    AutomationHandler,
    IntentClassifier,
    LLMBridge,
    RunningSTT,
    TTSAdapter,
    WakeWordDetector,
)
from friday.assistant_engine.models import (
    AudioFrame,
    EngineEvent,
    EventType,
    IntentResult,
    IntentType,
    LLMRequest,
    TranscriptUpdate,
)


def _configure_logger(level: str) -> logging.Logger:
    logger = logging.getLogger("friday.assistant_engine")
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    logger.setLevel(level.upper())
    logger.propagate = False
    return logger


class AssistantEngine:
    def __init__(
        self,
        config: EngineConfig,
        wake_word_detector: WakeWordDetector,
        stt: RunningSTT,
        intent_classifier: IntentClassifier,
        llm_bridge: LLMBridge,
        tts: TTSAdapter,
        automation: AutomationExecutor,
    ) -> None:
        self.config = config
        self.wake_word_detector = wake_word_detector
        self.stt = stt
        self.intent_classifier = intent_classifier
        self.llm_bridge = llm_bridge
        self.tts = tts
        self.automation = automation

        self.logger = _configure_logger(config.log_level)
        self._audio_queue: asyncio.Queue[AudioFrame] = asyncio.Queue(maxsize=config.queue_max_size)
        self._final_transcripts: asyncio.Queue[TranscriptUpdate] = asyncio.Queue(
            maxsize=config.queue_max_size
        )
        self._events: asyncio.Queue[EngineEvent] = asyncio.Queue(maxsize=config.queue_max_size * 2)
        self._tasks: list[asyncio.Task[None]] = []
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    async def start(self) -> None:
        if self._running:
            return
        self.logger.info("Starting assistant engine")
        self._running = True
        self._tasks = [
            asyncio.create_task(self._audio_loop(), name="assistant-audio-loop"),
            asyncio.create_task(self._decision_loop(), name="assistant-decision-loop"),
        ]
        await self._emit(
            EventType.ENGINE_STARTED,
            "engine",
            {"message": "assistant engine started"},
        )

    async def stop(self) -> None:
        if not self._running:
            return
        self.logger.info("Stopping assistant engine")
        self._running = False
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._tasks.clear()
        await self._emit(
            EventType.ENGINE_STOPPED,
            "engine",
            {"message": "assistant engine stopped"},
        )

    async def submit_audio(self, frame: AudioFrame) -> None:
        await self._audio_queue.put(frame)
        await self._emit(
            EventType.AUDIO_RECEIVED,
            frame.session_id,
            {"bytes": len(frame.payload), "is_final": frame.is_final},
        )

    async def submit_text(self, session_id: str, text: str, is_final: bool = True) -> None:
        await self.submit_audio(
            AudioFrame(
                session_id=session_id,
                payload=text.encode("utf-8"),
                is_final=is_final,
            )
        )

    async def events(self) -> AsyncIterator[EngineEvent]:
        while self._running or not self._events.empty():
            event = await self._events.get()
            yield event

    async def _audio_loop(self) -> None:
        while True:
            frame = await self._audio_queue.get()
            try:
                update = await self.stt.transcribe(frame)
            except Exception as exc:
                self.logger.exception("STT failure")
                await self._emit(
                    EventType.ERROR,
                    frame.session_id,
                    {"source": "stt", "message": str(exc)},
                )
                continue

            if not update.text:
                continue
            if update.is_final:
                await self._emit(
                    EventType.TRANSCRIPT_FINAL,
                    update.session_id,
                    {"text": update.text, "confidence": update.confidence},
                )
                await self._final_transcripts.put(update)
                continue
            await self._emit(
                EventType.TRANSCRIPT_PARTIAL,
                update.session_id,
                {"text": update.text, "confidence": update.confidence},
            )

    async def _decision_loop(self) -> None:
        while True:
            transcript = await self._final_transcripts.get()
            text = transcript.text.strip()
            if not text:
                continue

            command_text = text
            if self.config.require_wake_word:
                detected, command_text = self.wake_word_detector.detect(text)
                if not detected:
                    await self._emit(
                        EventType.WAKE_WORD_MISSED,
                        transcript.session_id,
                        {"transcript": text},
                    )
                    continue
                await self._emit(
                    EventType.WAKE_WORD_DETECTED,
                    transcript.session_id,
                    {"command": command_text},
                )

            intent = await self.intent_classifier.classify(command_text)
            await self._emit(
                EventType.INTENT_CLASSIFIED,
                transcript.session_id,
                {
                    "intent": intent.intent.value,
                    "confidence": intent.confidence,
                    "mode": intent.mode.value,
                },
            )

            llm_request = LLMRequest(
                session_id=transcript.session_id,
                prompt=_build_prompt(command_text, intent),
                intent=intent,
            )
            try:
                llm_response = await self.llm_bridge.generate(llm_request)
            except Exception as exc:
                self.logger.exception("LLM bridge failure")
                await self._emit(
                    EventType.ERROR,
                    transcript.session_id,
                    {"source": "llm", "message": str(exc)},
                )
                continue

            await self._emit(
                EventType.LLM_RESPONSE,
                transcript.session_id,
                {
                    "text": llm_response.text,
                    "backend": llm_response.backend,
                    "latency_ms": llm_response.latency_ms,
                },
            )

            if intent.intent == IntentType.AUTOMATION:
                action_name = _infer_action_name(intent)
                result = await self.automation.execute(action_name, intent.extracted_command)
                await self._emit(
                    EventType.AUTOMATION_EXECUTED,
                    transcript.session_id,
                    {
                        "action": result.action,
                        "success": result.success,
                        "message": result.message,
                        "data": result.data,
                    },
                )

            tts_result = await self.tts.speak(transcript.session_id, llm_response.text)
            await self._emit(
                EventType.TTS_READY,
                transcript.session_id,
                {
                    "audio_path": tts_result.audio_path,
                    "backend": tts_result.backend,
                },
            )

    async def _emit(self, event_type: EventType, session_id: str, payload: dict[str, object]) -> None:
        event = EngineEvent(event_type=event_type, session_id=session_id, payload=payload)
        await self._events.put(event)
        self.logger.debug("%s session=%s payload=%s", event_type.value, session_id, payload)

    def register_automation_handler(self, action_name: str, handler: AutomationHandler) -> None:
        register = getattr(self.automation, "register", None)
        if callable(register):
            register(action_name, handler)


def _build_prompt(command_text: str, intent: IntentResult) -> str:
    if intent.intent == IntentType.CODE:
        return f"Write practical code guidance for: {command_text}"
    if intent.intent == IntentType.AUTOMATION:
        return f"Confirm this automation request safely and clearly: {command_text}"
    return command_text


def _infer_action_name(intent: IntentResult) -> str:
    text = intent.extracted_command.lower()
    if text.startswith("open ") or text.startswith("launch "):
        return "open_app"
    if text.startswith("play "):
        return "media_control"
    if "remind me" in text or "set reminder" in text:
        return "reminder"
    return "default"


def build_default_engine(config: EngineConfig | None = None) -> AssistantEngine:
    cfg = config or EngineConfig.from_env()
    wake_word_detector = KeywordWakeWordDetector(cfg.wake_words)
    stt = RunningTextSTT(
        emit_partials=cfg.stt_emit_partials,
        min_partial_chars=cfg.stt_min_partial_chars,
    )
    intent_classifier = RuleBasedIntentClassifier()
    local_llm = LocalLLMBridge()
    cloud_llm = CloudLLMBridge(cfg) if cfg.cloud_llm_enabled else None
    llm_bridge = HybridLLMBridge(local_bridge=local_llm, cloud_bridge=cloud_llm)
    tts = FileTTSAdapter(cfg.tts_output_dir)
    automation = InProcessAutomationExecutor()
    automation.register("default", default_automation_handler)
    automation.register("open_app", default_automation_handler)
    automation.register("media_control", default_automation_handler)
    automation.register("reminder", default_automation_handler)
    return AssistantEngine(
        config=cfg,
        wake_word_detector=wake_word_detector,
        stt=stt,
        intent_classifier=intent_classifier,
        llm_bridge=llm_bridge,
        tts=tts,
        automation=automation,
    )
