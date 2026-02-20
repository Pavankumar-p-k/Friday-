from __future__ import annotations

from dataclasses import dataclass, field

from friday.assistant_engine.interfaces import RunningSTT
from friday.assistant_engine.models import AudioFrame, TranscriptUpdate


@dataclass
class RunningTextSTT(RunningSTT):
    emit_partials: bool = True
    min_partial_chars: int = 8
    _buffers: dict[str, str] = field(default_factory=dict)

    async def transcribe(self, frame: AudioFrame) -> TranscriptUpdate:
        text_chunk = frame.payload.decode("utf-8", errors="ignore")
        existing = self._buffers.get(frame.session_id, "")
        combined = f"{existing}{text_chunk}"

        if frame.is_final:
            final_text = combined.strip()
            self._buffers.pop(frame.session_id, None)
            return TranscriptUpdate(
                session_id=frame.session_id,
                text=final_text,
                is_final=True,
                confidence=0.72 if final_text else 0.0,
                backend="running-text",
            )

        self._buffers[frame.session_id] = combined
        partial = combined.strip()
        if not self.emit_partials or len(partial) < self.min_partial_chars:
            return TranscriptUpdate(
                session_id=frame.session_id,
                text="",
                is_final=False,
                confidence=0.0,
                backend="running-text",
            )
        return TranscriptUpdate(
            session_id=frame.session_id,
            text=partial,
            is_final=False,
            confidence=0.45,
            backend="running-text",
        )
