from __future__ import annotations

from pathlib import Path
import shlex
import subprocess
import uuid

from friday.config import Settings


class VoicePipeline:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.input_dir = settings.voice_input_dir
        self.output_dir = settings.voice_output_dir
        self.input_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def transcribe(self, audio_path: Path) -> dict[str, str]:
        if not audio_path.exists():
            return {"text": "", "backend": "none", "warning": f"File not found: {audio_path}"}

        if self.settings.voice_stt_command.strip():
            text = self._run_stt_command(audio_path)
            if text:
                return {"text": text, "backend": "command", "warning": ""}

        if audio_path.suffix.lower() == ".txt":
            try:
                text = audio_path.read_text(encoding="utf-8", errors="ignore").strip()
                return {"text": text, "backend": "txt-fallback", "warning": ""}
            except Exception as exc:
                return {"text": "", "backend": "txt-fallback", "warning": str(exc)}

        return {
            "text": "",
            "backend": "none",
            "warning": (
                "No STT backend configured. Set FRIDAY_VOICE_STT_COMMAND or pass .txt input for fallback."
            ),
        }

    async def synthesize(self, text: str) -> dict[str, str]:
        safe_text = text.strip()
        if not safe_text:
            return {"audio_path": "", "backend": "none", "warning": "Text is empty"}

        target = self.output_dir / f"reply_{uuid.uuid4().hex[:10]}.wav"
        if self.settings.voice_tts_command.strip():
            ok = self._run_tts_command(text=safe_text, output_path=target)
            if ok:
                return {"audio_path": str(target), "backend": "command", "warning": ""}

        fallback = self.output_dir / f"reply_{uuid.uuid4().hex[:10]}.txt"
        fallback.write_text(safe_text, encoding="utf-8")
        return {
            "audio_path": str(fallback),
            "backend": "text-fallback",
            "warning": (
                "No TTS backend configured. Set FRIDAY_VOICE_TTS_COMMAND to generate audio."
            ),
        }

    def save_upload(self, filename: str, content: bytes) -> Path:
        clean_name = Path(filename).name or "voice_input.bin"
        target = self.input_dir / f"{uuid.uuid4().hex[:10]}_{clean_name}"
        target.write_bytes(content)
        return target

    def wake_word_detected(self, text: str) -> bool:
        lowered = text.lower()
        return any(wake_word.lower() in lowered for wake_word in self.settings.voice_wake_words)

    def _run_stt_command(self, audio_path: Path) -> str:
        command = self.settings.voice_stt_command.format(audio_path=str(audio_path))
        try:
            result = subprocess.run(
                shlex.split(command),
                capture_output=True,
                text=True,
                timeout=self.settings.request_timeout_sec,
            )
            if result.returncode != 0:
                return ""
            output = result.stdout.strip()
            return output
        except Exception:
            return ""

    def _run_tts_command(self, text: str, output_path: Path) -> bool:
        command = self.settings.voice_tts_command.format(
            text=text.replace('"', ""),
            output_path=str(output_path),
        )
        try:
            result = subprocess.run(
                shlex.split(command),
                capture_output=True,
                text=True,
                timeout=self.settings.request_timeout_sec,
            )
            return result.returncode == 0 and output_path.exists()
        except Exception:
            return False

