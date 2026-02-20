from __future__ import annotations

import asyncio
from pathlib import Path
import uuid

from friday.assistant_engine.interfaces import TTSAdapter
from friday.assistant_engine.models import TTSResult


class FileTTSAdapter(TTSAdapter):
    def __init__(self, output_dir: Path) -> None:
        self._output_dir = output_dir
        self._output_dir.mkdir(parents=True, exist_ok=True)

    async def speak(self, session_id: str, text: str) -> TTSResult:
        return await asyncio.to_thread(self._write_text_fallback, session_id, text)

    def _write_text_fallback(self, session_id: str, text: str) -> TTSResult:
        safe_session = session_id.replace(" ", "_")
        path = self._output_dir / f"{safe_session}_{uuid.uuid4().hex[:10]}.txt"
        path.write_text(text.strip(), encoding="utf-8")
        return TTSResult(audio_path=str(path), backend="text-fallback")
