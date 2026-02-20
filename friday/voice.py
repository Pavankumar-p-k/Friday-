from __future__ import annotations

import asyncio
from pathlib import Path
import re
import shlex
import subprocess
from typing import Any
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
        return await asyncio.to_thread(self._transcribe_sync, audio_path)

    def _transcribe_sync(self, audio_path: Path) -> dict[str, str]:
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
        return await asyncio.to_thread(self._synthesize_sync, text)

    def _synthesize_sync(self, text: str) -> dict[str, str]:
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

    def allocate_upload_path(self, filename: str) -> Path:
        clean_name = Path(filename).name or "voice_input.bin"
        return self.input_dir / f"{uuid.uuid4().hex[:10]}_{clean_name}"

    def save_upload(self, filename: str, content: bytes) -> Path:
        if len(content) > self.settings.voice_max_upload_bytes:
            raise ValueError(
                f"Upload exceeds limit ({self.settings.voice_max_upload_bytes} bytes)."
            )
        target = self.allocate_upload_path(filename)
        target.write_bytes(content)
        return target

    def wake_word_detected(self, text: str) -> bool:
        lowered = text.lower()
        return any(wake_word.lower() in lowered for wake_word in self.settings.voice_wake_words)

    def parse_wake_command(self, text: str) -> tuple[bool, str]:
        wake_words = [item.strip() for item in self.settings.voice_wake_words if item.strip()]
        if not wake_words:
            return False, text.strip()
        pattern = r"|".join(re.escape(item) for item in wake_words)
        match = re.match(
            rf"^\s*(?:hey|ok|okay)?\s*(?:{pattern})\b[\s,:\-]*(?P<command>.*)$",
            text,
            flags=re.IGNORECASE,
        )
        if match is None:
            return False, text.strip()
        return True, match.group("command").strip()

    def capture_once(self) -> dict[str, str]:
        command_template = self.settings.voice_loop_capture_command.strip()
        if not command_template:
            return {"backend": "none", "path": "", "transcript": "", "warning": ""}

        target = self.input_dir / f"loop_{uuid.uuid4().hex[:10]}.wav"
        result = self._run_capture_command(command_template=command_template, output_path=target)
        return {
            "backend": result.get("backend", "none"),
            "path": result.get("path", ""),
            "transcript": result.get("transcript", ""),
            "warning": result.get("warning", ""),
        }

    def next_inbox_file(self, seen_files: set[str]) -> Path | None:
        try:
            candidates = sorted(
                (item for item in self.input_dir.iterdir() if item.is_file()),
                key=lambda path: path.stat().st_mtime,
            )
        except FileNotFoundError:
            return None

        for path in candidates:
            key = str(path.resolve())
            if key in seen_files:
                continue
            seen_files.add(key)
            return path
        return None

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

    def _run_capture_command(self, command_template: str, output_path: Path) -> dict[str, Any]:
        command = command_template.format(output_path=str(output_path))
        try:
            result = subprocess.run(
                shlex.split(command),
                capture_output=True,
                text=True,
                timeout=self.settings.request_timeout_sec,
            )
        except Exception as exc:
            return {"backend": "capture-command", "path": "", "transcript": "", "warning": str(exc)}

        if result.returncode != 0:
            message = result.stderr.strip() or result.stdout.strip() or "capture command failed"
            return {"backend": "capture-command", "path": "", "transcript": "", "warning": message}

        stdout = result.stdout.strip()
        if output_path.exists():
            return {
                "backend": "capture-command",
                "path": str(output_path),
                "transcript": "",
                "warning": "",
            }

        if stdout:
            candidate = Path(stdout)
            if candidate.exists():
                return {
                    "backend": "capture-command",
                    "path": str(candidate),
                    "transcript": "",
                    "warning": "",
                }
            return {
                "backend": "capture-command",
                "path": "",
                "transcript": stdout,
                "warning": "",
            }

        return {
            "backend": "capture-command",
            "path": "",
            "transcript": "",
            "warning": "capture command produced no output",
        }
